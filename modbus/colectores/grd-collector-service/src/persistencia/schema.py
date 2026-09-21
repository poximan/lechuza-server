from __future__ import annotations

import os
import sqlite3
import tempfile

from .configuracion_base_datos import DATABASE_FILE


SCHEMA_VERSION = 1
SCHEMA_SQL = """
PRAGMA foreign_keys = ON;
BEGIN IMMEDIATE;
CREATE TABLE grd (
    id INTEGER PRIMARY KEY,
    descripcion TEXT NOT NULL CHECK (length(trim(descripcion)) > 0),
    activo INTEGER NOT NULL CHECK (activo IN (0, 1))
);
CREATE TABLE historicos (
    id_grd INTEGER NOT NULL,
    timestamp TEXT NOT NULL CHECK (
        length(timestamp) = 20
        AND timestamp GLOB '????-??-??T??:??:??Z'
        AND datetime(timestamp) IS NOT NULL
    ),
    conectado INTEGER NOT NULL CHECK (conectado IN (0, 1)),
    PRIMARY KEY (id_grd, timestamp),
    FOREIGN KEY (id_grd) REFERENCES grd(id)
) WITHOUT ROWID;
CREATE TABLE grd_estado_actual (
    id_grd INTEGER PRIMARY KEY,
    timestamp TEXT NOT NULL CHECK (
        length(timestamp) = 20
        AND timestamp GLOB '????-??-??T??:??:??Z'
        AND datetime(timestamp) IS NOT NULL
    ),
    conectado INTEGER NOT NULL CHECK (conectado IN (0, 1)),
    FOREIGN KEY (id_grd) REFERENCES grd(id)
);
PRAGMA user_version = 1;
COMMIT;
"""
EXPECTED_COLUMNS = {
    "grd": {"id", "descripcion", "activo"},
    "historicos": {"id_grd", "timestamp", "conectado"},
    "grd_estado_actual": {"id_grd", "timestamp", "conectado"},
}
EXPECTED_PRIMARY_KEYS = {
    "grd": ["id"],
    "historicos": ["id_grd", "timestamp"],
    "grd_estado_actual": ["id_grd"],
}
EXPECTED_FOREIGN_KEYS = {
    "grd": set(),
    "historicos": {("id_grd", "grd", "id")},
    "grd_estado_actual": {("id_grd", "grd", "id")},
}
EXPECTED_NOT_NULL = {
    "grd": {"descripcion", "activo"},
    "historicos": {"id_grd", "timestamp", "conectado"},
    "grd_estado_actual": {"timestamp", "conectado"},
}


def ensure_database() -> None:
    if not os.path.isfile(DATABASE_FILE):
        os.makedirs(os.path.dirname(DATABASE_FILE), exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(
            prefix="grd-schema-",
            suffix=".db",
            dir=os.path.dirname(DATABASE_FILE),
        )
        os.close(descriptor)
        try:
            with sqlite3.connect(temporary) as conn:
                conn.executescript(SCHEMA_SQL)
            os.chmod(temporary, 0o600)
            os.replace(temporary, DATABASE_FILE)
        finally:
            if os.path.exists(temporary):
                os.remove(temporary)
    validate_database()


def validate_database() -> None:
    with sqlite3.connect(f"file:{DATABASE_FILE}?mode=ro", uri=True) as conn:
        version = int(conn.execute("PRAGMA user_version").fetchone()[0])
        if version != SCHEMA_VERSION:
            raise RuntimeError(
                f"Version GRD invalida: esperada={SCHEMA_VERSION}, encontrada={version}"
            )
        for table, expected in EXPECTED_COLUMNS.items():
            rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
            found = {str(row[1]) for row in rows}
            if found != expected:
                raise RuntimeError(
                    f"Contrato GRD invalido en {table}: {sorted(found)}"
                )
            primary_key = [
                str(row[1])
                for row in sorted(rows, key=lambda row: int(row[5]))
                if int(row[5])
            ]
            if primary_key != EXPECTED_PRIMARY_KEYS[table]:
                raise RuntimeError(f"Clave primaria GRD invalida en {table}")
            not_null = {str(row[1]) for row in rows if int(row[3])}
            if not_null != EXPECTED_NOT_NULL[table]:
                raise RuntimeError(f"Restricciones GRD invalidas en {table}")
            foreign_keys = {
                (str(row[3]), str(row[2]), str(row[4]))
                for row in conn.execute(f"PRAGMA foreign_key_list({table})").fetchall()
            }
            if foreign_keys != EXPECTED_FOREIGN_KEYS[table]:
                raise RuntimeError(f"Claves foraneas GRD invalidas en {table}")
        integrity = conn.execute("PRAGMA integrity_check").fetchone()
        if not integrity or integrity[0] != "ok":
            raise RuntimeError(f"Integridad GRD invalida: {integrity}")
        if conn.execute("PRAGMA foreign_key_check").fetchall():
            raise RuntimeError("La base GRD viola claves foraneas")
        history_sql = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='historicos'"
        ).fetchone()
        if not history_sql or "WITHOUT ROWID" not in str(history_sql[0]).upper():
            raise RuntimeError("historicos debe usar WITHOUT ROWID")
