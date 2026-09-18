import hashlib
import json
import os
import sqlite3
from threading import Lock
from typing import Iterable, Optional

from timeauthority import get_time_authority

from . import config


_db_lock = Lock()
_AUTH = get_time_authority()


class IdempotencyConflictError(Exception):
    pass


class QueueCapacityError(Exception):
    pass


def init_db():
    os.makedirs(config.DATABASE_DIR, exist_ok=True)
    with _get_conn() as conn:
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS mensajes_enviados (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                subject TEXT NOT NULL,
                body TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                message_type TEXT,
                recipient TEXT,
                success INTEGER NOT NULL
            );
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS mensajes_pendientes (
                idempotency_key TEXT PRIMARY KEY,
                payload_hash TEXT NOT NULL,
                recipients TEXT NOT NULL,
                subject TEXT NOT NULL,
                body TEXT NOT NULL,
                message_type TEXT,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                last_error TEXT
            );
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_mensajes_pendientes_status_created
            ON mensajes_pendientes(status, created_at);
            """
        )
        _migrate_legacy_history(conn)
        # Un envio interrumpido no se repite: SMTP no permite distinguir
        # con certeza entre "no enviado" y "enviado sin respuesta final".
        conn.execute(
            """
            UPDATE mensajes_pendientes
            SET status = 'failed',
                updated_at = ?,
                last_error = 'envio interrumpido; no se reintenta para evitar duplicados'
            WHERE status = 'processing';
            """,
            (_AUTH.utc_iso(),),
        )
        conn.commit()


def _normalize_legacy_timestamp(value: str) -> str:
    parsed = _AUTH.parse(value, assume_utc_on_naive=True)
    return _AUTH.utc_iso(parsed)


def _migrate_legacy_history(conn: sqlite3.Connection) -> None:
    """Incorpora envios previos a la cola durable sin duplicar los actuales."""
    rows = conn.execute(
        """
        SELECT subject, body, timestamp, message_type, recipient, success
        FROM mensajes_enviados
        ORDER BY id ASC;
        """
    ).fetchall()
    grouped: dict[tuple, dict] = {}
    for row in rows:
        timestamp = _normalize_legacy_timestamp(str(row["timestamp"]))
        key = (
            str(row["subject"]),
            str(row["body"]),
            timestamp,
            row["message_type"],
        )
        group = grouped.setdefault(key, {"recipients": [], "success": []})
        recipient = str(row["recipient"] or "").strip()
        if recipient and recipient not in group["recipients"]:
            group["recipients"].append(recipient)
        group["success"].append(bool(row["success"]))

    for (subject, body, timestamp, message_type), group in grouped.items():
        exists = conn.execute(
            """
            SELECT 1 FROM mensajes_pendientes
            WHERE subject = ? AND body = ? AND message_type IS ?
              AND updated_at = ?
            LIMIT 1;
            """,
            (subject, body, message_type, timestamp),
        ).fetchone()
        if exists is not None:
            continue
        identity = json.dumps(
            [subject, body, timestamp, message_type, group["recipients"]],
            ensure_ascii=False,
            separators=(",", ":"),
        )
        legacy_key = "legacy:" + hashlib.sha256(identity.encode("utf-8")).hexdigest()
        succeeded = all(group["success"])
        conn.execute(
            """
            INSERT OR IGNORE INTO mensajes_pendientes (
                idempotency_key, payload_hash, recipients, subject, body,
                message_type, status, created_at, updated_at, last_error
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                legacy_key,
                _payload_hash(group["recipients"], subject, body, message_type),
                json.dumps(group["recipients"], ensure_ascii=False),
                subject,
                body,
                message_type,
                "sent" if succeeded else "failed",
                timestamp,
                timestamp,
                None if succeeded else "envio historico con destinatarios fallidos",
            ),
        )


def _get_conn():
    conn = sqlite3.connect(config.DATABASE_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _payload_hash(
    recipients: Iterable[str],
    subject: str,
    body: str,
    message_type: Optional[str],
) -> str:
    canonical = json.dumps(
        {
            "recipients": list(recipients),
            "subject": subject,
            "body": body,
            "message_type": message_type,
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def reserve_message(
    idempotency_key: str,
    recipients: Iterable[str],
    subject: str,
    body: str,
    message_type: Optional[str],
) -> tuple[bool, str]:
    recipients_list = list(recipients)
    payload_hash = _payload_hash(recipients_list, subject, body, message_type)
    now = _AUTH.utc_iso()

    with _db_lock:
        with _get_conn() as conn:
            conn.execute("BEGIN IMMEDIATE;")
            existing = conn.execute(
                """
                SELECT payload_hash, status
                FROM mensajes_pendientes
                WHERE idempotency_key = ?;
                """,
                (idempotency_key,),
            ).fetchone()
            if existing is not None:
                if str(existing["payload_hash"]) != payload_hash:
                    raise IdempotencyConflictError(
                        "la clave idempotente ya existe con otro contenido"
                    )
                return False, str(existing["status"])

            active_count = conn.execute(
                """
                SELECT COUNT(*) AS total
                FROM mensajes_pendientes
                WHERE status IN ('pending', 'processing');
                """
            ).fetchone()["total"]
            if int(active_count) >= config.QUEUE_MAXSIZE:
                raise QueueCapacityError("cola llena, intentar mas tarde")

            conn.execute(
                """
                INSERT INTO mensajes_pendientes (
                    idempotency_key, payload_hash, recipients, subject, body,
                    message_type, status, created_at, updated_at, last_error
                )
                VALUES (?, ?, ?, ?, ?, ?, 'pending', ?, ?, NULL);
                """,
                (
                    idempotency_key,
                    payload_hash,
                    json.dumps(recipients_list, ensure_ascii=False),
                    subject,
                    body,
                    message_type,
                    now,
                    now,
                ),
            )
            return True, "pending"


def claim_message(idempotency_key: str | None = None) -> dict | None:
    with _db_lock:
        with _get_conn() as conn:
            conn.execute("BEGIN IMMEDIATE;")
            if idempotency_key:
                row = conn.execute(
                    """
                    SELECT *
                    FROM mensajes_pendientes
                    WHERE idempotency_key = ? AND status = 'pending';
                    """,
                    (idempotency_key,),
                ).fetchone()
            else:
                row = conn.execute(
                    """
                    SELECT *
                    FROM mensajes_pendientes
                    WHERE status = 'pending'
                    ORDER BY created_at ASC
                    LIMIT 1;
                    """
                ).fetchone()
            if row is None:
                return None

            cursor = conn.execute(
                """
                UPDATE mensajes_pendientes
                SET status = 'processing', updated_at = ?
                WHERE idempotency_key = ? AND status = 'pending';
                """,
                (_AUTH.utc_iso(), row["idempotency_key"]),
            )
            if cursor.rowcount != 1:
                return None

            return {
                "idempotency_key": str(row["idempotency_key"]),
                "recipients": json.loads(str(row["recipients"])),
                "subject": str(row["subject"]),
                "body": str(row["body"]),
                "message_type": row["message_type"],
            }


def has_pending_message() -> bool:
    with _db_lock:
        with _get_conn() as conn:
            return conn.execute(
                "SELECT 1 FROM mensajes_pendientes WHERE status = 'pending' LIMIT 1"
            ).fetchone() is not None


def complete_message(task: dict, success: bool, error: str = "") -> None:
    status = "sent" if success else "failed"
    with _db_lock:
        with _get_conn() as conn:
            conn.execute("BEGIN IMMEDIATE;")
            cursor = conn.execute(
                """
                UPDATE mensajes_pendientes
                SET status = ?, updated_at = ?, last_error = ?
                WHERE idempotency_key = ? AND status = 'processing';
                """,
                (status, _AUTH.utc_iso(), error or None, task["idempotency_key"]),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("La solicitud de correo ya no esta en procesamiento")
            timestamp = _AUTH.utc_iso()
            conn.executemany(
                """
                INSERT INTO mensajes_enviados (
                    subject, body, timestamp, message_type, recipient, success
                ) VALUES (?, ?, ?, ?, ?, ?);
                """,
                [
                    (
                        task["subject"],
                        task["body"],
                        timestamp,
                        task.get("message_type"),
                        recipient,
                        1 if success else 0,
                    )
                    for recipient in task["recipients"]
                ],
            )
            conn.commit()


def list_dispatches(message_type: str, limit: int = 2000) -> list[dict]:
    """Contrato de lectura del despacho; mensagelo conserva la propiedad de su cola."""
    safe_limit = min(5000, max(1, int(limit)))
    with _db_lock:
        with _get_conn() as conn:
            rows = conn.execute(
                """
                SELECT idempotency_key, recipients, subject, message_type, status,
                       created_at, updated_at, last_error
                FROM mensajes_pendientes
                WHERE message_type = ?
                ORDER BY created_at DESC, idempotency_key DESC
                LIMIT ?;
                """,
                (message_type, safe_limit),
            ).fetchall()
            return [
                {
                    "idempotency_key": str(row["idempotency_key"]),
                    "recipients": json.loads(str(row["recipients"])),
                    "subject": str(row["subject"]),
                    "message_type": row["message_type"],
                    "status": str(row["status"]),
                    "created_at": str(row["created_at"]),
                    "updated_at": str(row["updated_at"]),
                    "last_error": row["last_error"],
                }
                for row in rows
            ]


def list_messages(limit: int = 200, offset: int = 0) -> tuple[list[dict], int]:
    """Historial durable de solicitudes; es la unica fuente de verdad de Mensagelo."""
    safe_limit = min(1000, max(1, int(limit)))
    safe_offset = max(0, int(offset))
    with _db_lock:
        with _get_conn() as conn:
            total = int(
                conn.execute("SELECT COUNT(*) FROM mensajes_pendientes").fetchone()[0]
            )
            rows = conn.execute(
                """
                SELECT idempotency_key, recipients, subject, body, message_type,
                       status, created_at, updated_at, last_error
                FROM mensajes_pendientes
                ORDER BY created_at DESC, idempotency_key DESC
                LIMIT ? OFFSET ?
                """,
                (safe_limit, safe_offset),
            ).fetchall()
    items = [
        {
            "idempotency_key": str(row["idempotency_key"]),
            "recipients": json.loads(str(row["recipients"])),
            "subject": str(row["subject"]),
            "body": str(row["body"]),
            "message_type": row["message_type"],
            "status": str(row["status"]),
            "created_at": str(row["created_at"]),
            "updated_at": str(row["updated_at"]),
            "last_error": row["last_error"],
        }
        for row in rows
    ]
    return items, total
