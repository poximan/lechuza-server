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


def complete_message(idempotency_key: str, success: bool, error: str = "") -> None:
    status = "sent" if success else "failed"
    with _db_lock:
        with _get_conn() as conn:
            conn.execute(
                """
                UPDATE mensajes_pendientes
                SET status = ?, updated_at = ?, last_error = ?
                WHERE idempotency_key = ? AND status = 'processing';
                """,
                (status, _AUTH.utc_iso(), error or None, idempotency_key),
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
                ORDER BY created_at DESC
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


def log_message(
    subject: str,
    body: str,
    recipients: Iterable[str],
    success: bool,
    message_type: Optional[str] = None,
):
    with _db_lock:
        with _get_conn() as conn:
            rows = [
                (
                    subject,
                    body,
                    _AUTH.utc_iso(),
                    message_type,
                    recipient,
                    1 if success else 0,
                )
                for recipient in recipients
            ]
            conn.executemany(
                """
                INSERT INTO mensajes_enviados (
                    subject, body, timestamp, message_type, recipient, success
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
            conn.commit()
