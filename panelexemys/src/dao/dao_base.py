import os
import sqlite3
import threading
from pathlib import Path

from src.startup_errors import PanelexemysPersistenceError


_DATA_DIR_ENV = "PANELEXEMYS_DATA_DIR"


def _pick_db_path() -> Path:
    data_dir = os.getenv(_DATA_DIR_ENV)
    if data_dir and data_dir.strip():
        return Path(data_dir) / "panelexemys.db"

    raise EnvironmentError(f"Falta variable de entorno obligatoria: {_DATA_DIR_ENV}")


def _write_state(path: Path) -> str:
    parent = path.parent
    details = [
        f"directorio={parent}",
        f"directorio_existe={parent.exists()}",
        f"directorio_escribible={os.access(parent, os.W_OK)}",
        f"base_existe={path.exists()}",
    ]
    if path.exists():
        details.append(f"base_escribible={os.access(path, os.W_OK)}")
    return ", ".join(details)


def _persistence_error(action: str, path: Path, exc: BaseException) -> PanelexemysPersistenceError:
    data_dir = os.getenv(_DATA_DIR_ENV, "")
    message = "\n".join(
        [
            "ERROR FATAL: panelexemys no puede inicializar su persistencia local.",
            f"Accion fallida: {action}.",
            f"Variable {_DATA_DIR_ENV}: {data_dir or '<vacia>'}",
            f"Base SQLite esperada: {path}",
            f"Diagnostico de permisos: {_write_state(path)}",
            f"Causa tecnica: {type(exc).__name__}: {exc}",
            "Revise que el volumen ./volumes/panelexemys este montado en /app/data y sea escribible por el usuario del contenedor.",
            "Si existe panelexemys.db, tambien debe ser escribible; SQLite necesita crear o escribir archivos -wal y -shm junto a la base.",
            "El servicio se detiene sin fallback para evitar operar con persistencia inconsistente.",
        ]
    )
    return PanelexemysPersistenceError(message)


def _is_storage_permission_error(exc: sqlite3.OperationalError) -> bool:
    text = str(exc).lower()
    return any(
        fragment in text
        for fragment in (
            "readonly database",
            "read-only database",
            "attempt to write",
            "unable to open database file",
        )
    )


def _safe_path(path: Path) -> Path:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        return path
    except (PermissionError, FileNotFoundError, OSError) as exc:
        raise _persistence_error("crear directorio de datos", path, exc) from exc


_db_path = _safe_path(_pick_db_path())

_connection_lock = threading.RLock()


def get_db_path() -> Path:
    return _db_path


def _configure_connection(conn: sqlite3.Connection) -> sqlite3.Connection:
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
    except sqlite3.OperationalError as exc:
        if _is_storage_permission_error(exc):
            raise _persistence_error("configurar SQLite en modo WAL", _db_path, exc) from exc
        raise
    return conn


def get_db_connection() -> sqlite3.Connection:
    conn = None
    try:
        conn = sqlite3.connect(_db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return _configure_connection(conn)
    except PanelexemysPersistenceError:
        if conn is not None:
            conn.close()
        raise
    except sqlite3.OperationalError as exc:
        if _is_storage_permission_error(exc):
            raise _persistence_error("abrir base SQLite", _db_path, exc) from exc
        raise


def with_connection(fn, *args, **kwargs):
    with _connection_lock:
        try:
            with get_db_connection() as conn:
                return fn(conn, *args, **kwargs)
        except sqlite3.OperationalError as exc:
            if _is_storage_permission_error(exc):
                raise _persistence_error("ejecutar operacion SQLite", _db_path, exc) from exc
            raise
