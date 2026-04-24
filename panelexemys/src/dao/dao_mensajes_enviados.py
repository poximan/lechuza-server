from __future__ import annotations

import json
import threading
from typing import Sequence

from .dao_base import get_db_connection, with_connection


class MensajesEnviadosDAO:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        def _init(conn):
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS mensajes_enviados (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    body TEXT NOT NULL,
                    message_type TEXT NOT NULL,
                    recipients TEXT NOT NULL,
                    success INTEGER NOT NULL,
                    created_at TEXT DEFAULT (datetime('now'))
                );
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_mensajes_ts ON mensajes_enviados(ts);"
            )

        with self._lock:
            with_connection(_init)

    def insert_sent_message(
        self,
        subject: str,
        body: str,
        timestamp: str,
        message_type: str,
        recipients: Sequence[str] | str,
        success: bool,
    ) -> None:
        if isinstance(recipients, str):
            recipients_serialized = recipients
        else:
            recipients_serialized = json.dumps(list(recipients))

        payload = (
            timestamp,
            subject[:512],
            body[:4096],
            message_type[:128],
            recipients_serialized,
            int(bool(success)),
        )

        def _insert(conn):
            conn.execute(
                """
                INSERT INTO mensajes_enviados (ts, subject, body, message_type, recipients, success)
                VALUES (?, ?, ?, ?, ?, ?);
                """,
                payload,
            )

        with self._lock:
            with_connection(_insert)


mensajes_enviados_dao = MensajesEnviadosDAO()
