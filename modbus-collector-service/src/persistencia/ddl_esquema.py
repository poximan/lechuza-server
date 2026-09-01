from __future__ import annotations

import argparse
import os
import sqlite3

from src.persistencia.configuracion_base_datos import DATABASE_FILE


SCHEMA_VERSION = 5

SCHEMA_SQL = f"""
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

CREATE TABLE reles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    id_modbus INTEGER NOT NULL UNIQUE,
    descripcion TEXT NOT NULL CHECK (length(trim(descripcion)) > 0)
);

CREATE TABLE fallas_reles (
    id_rele INTEGER PRIMARY KEY NOT NULL,
    numero_falla INTEGER NOT NULL,
    timestamp TEXT NOT NULL CHECK (
        length(timestamp) = 24
        AND timestamp GLOB '????-??-??T??:??:??.???Z'
        AND datetime(timestamp) IS NOT NULL
    ),
    formato_timestamp TEXT NOT NULL CHECK (
        formato_timestamp IN ('private', 'iec870')
    ),
    fasea_corr INTEGER,
    faseb_corr INTEGER,
    fasec_corr INTEGER,
    tierra_corr INTEGER,
    FOREIGN KEY (id_rele) REFERENCES reles(id)
);

PRAGMA user_version = {SCHEMA_VERSION};
COMMIT;
"""


def create_new_database(database_file: str = DATABASE_FILE) -> None:
    """Crea una base nueva y se niega a tocar un archivo existente."""
    target = os.path.abspath(database_file)
    os.makedirs(os.path.dirname(target), exist_ok=True)

    try:
        descriptor = os.open(target, os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o600)
    except FileExistsError as exc:
        raise FileExistsError(
            f"El DDL se niega a sobrescribir la base existente: {target}"
        ) from exc
    os.close(descriptor)

    conn: sqlite3.Connection | None = None
    try:
        conn = sqlite3.connect(target)
        conn.executescript(SCHEMA_SQL)
        result = conn.execute("PRAGMA integrity_check;").fetchone()
        if result is None or result[0] != "ok":
            raise RuntimeError(f"SQLite integrity_check fallo para {target}: {result}")
    except Exception:
        if conn is not None:
            conn.close()
        try:
            os.remove(target)
        except OSError:
            pass
        raise
    else:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Crea desde cero la base operativa de modbus-collector-service."
    )
    parser.add_argument("--database", default=DATABASE_FILE, help="Ruta de la base nueva")
    args = parser.parse_args()
    create_new_database(args.database)
    print(f"Base nueva creada con esquema {SCHEMA_VERSION}: {os.path.abspath(args.database)}")


if __name__ == "__main__":
    main()
