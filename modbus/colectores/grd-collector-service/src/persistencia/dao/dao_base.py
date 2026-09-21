import os
import sqlite3

from src.persistencia.configuracion_base_datos import DATABASE_FILE


SQLITE_TIMEOUT_SECONDS = 10


def get_db_connection() -> sqlite3.Connection:
    """Abre la base operativa existente sin crearla implicitamente."""
    if not os.path.isfile(DATABASE_FILE):
        raise FileNotFoundError(
            f"No existe la base operativa {DATABASE_FILE}. "
            "Debe aprovisionarse antes de iniciar el servicio."
        )

    conn = sqlite3.connect(DATABASE_FILE, timeout=SQLITE_TIMEOUT_SECONDS)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute(f"PRAGMA busy_timeout = {SQLITE_TIMEOUT_SECONDS * 1000};")
    conn.execute("PRAGMA temp_store = MEMORY;")
    return conn
