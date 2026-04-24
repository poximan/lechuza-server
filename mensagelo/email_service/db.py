import os
import sqlite3
from threading import Lock
from typing import Optional, Iterable
from timeauthority import get_time_authority
from . import config

_db_lock = Lock()
_AUTH = get_time_authority()

def init_db():
    os.makedirs(config.DATABASE_DIR, exist_ok=True)
    with _get_conn() as conn:
        cur = conn.cursor()
        cur.execute("PRAGMA foreign_keys = ON;")
        # Tabla clonada de tu esquema
        cur.execute("""
            CREATE TABLE IF NOT EXISTS mensajes_enviados (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                subject TEXT NOT NULL,
                body TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                message_type TEXT,
                recipient TEXT,
                success INTEGER NOT NULL
            );
        """)
        conn.commit()

def _get_conn():
    # check_same_thread=False para permitir uso desde hilo worker
    return sqlite3.connect(config.DATABASE_PATH, check_same_thread=False)

def log_message(subject: str, body: str, recipients: Iterable[str], success: bool, message_type: Optional[str] = None):
    with _db_lock:
        with _get_conn() as conn:
            cur = conn.cursor()
            rows = [
                (subject, body, _AUTH.utc_iso(), message_type, r, 1 if success else 0)
                for r in recipients
            ]
            cur.executemany("""
                INSERT INTO mensajes_enviados (subject, body, timestamp, message_type, recipient, success)
                VALUES (?, ?, ?, ?, ?, ?)
            """, rows)
            conn.commit()
