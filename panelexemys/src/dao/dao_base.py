import os
import sqlite3
import threading
from pathlib import Path


def _pick_db_path() -> Path:
    explicit = os.getenv("PANELEXEMYS_DB_PATH")
    if explicit and explicit.strip():
        return Path(explicit)

    data_dir = os.getenv("PANELEXEMYS_DATA_DIR")
    if data_dir and data_dir.strip():
        return Path(data_dir) / "panelexemys.db"

    raise EnvironmentError("Falta variable de entorno obligatoria: PANELEXEMYS_DB_PATH o PANELEXEMYS_DATA_DIR")


def _safe_path(path: Path) -> Path:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        return path
    except (PermissionError, FileNotFoundError) as exc:
        raise EnvironmentError(f"No se pudo crear el directorio de la base: {exc}") from exc


_db_path = _safe_path(_pick_db_path())

_connection_lock = threading.RLock()


def get_db_path() -> Path:
    return _db_path


def _configure_connection(conn: sqlite3.Connection) -> sqlite3.Connection:
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def get_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return _configure_connection(conn)


def with_connection(fn, *args, **kwargs):
    with _connection_lock:
        with get_db_connection() as conn:
            return fn(conn, *args, **kwargs)
