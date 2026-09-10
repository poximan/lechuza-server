from __future__ import annotations

import argparse
import os
import sqlite3

from src.persistencia.configuracion_base_datos import DATABASE_FILE


SCHEMA_VERSION = 8

FALLAS_RELES_TABLE_SQL = """
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
)
"""

OSCILOPERTURBOGRAMAS_TABLE_SQL = """
CREATE TABLE osciloperturbogramas_reles (
    id_rele INTEGER NOT NULL REFERENCES reles(id),
    registro INTEGER NOT NULL CHECK (registro BETWEEN 1 AND 5),
    timestamp TEXT NOT NULL CHECK (
        length(timestamp) = 24
        AND timestamp GLOB '????-??-??T??:??:??.???Z'
        AND datetime(timestamp) IS NOT NULL
    ),
    descargado_en TEXT CHECK (
        descargado_en IS NULL
        OR (
            length(descargado_en) = 24
            AND descargado_en GLOB '????-??-??T??:??:??.???Z'
            AND datetime(descargado_en) IS NOT NULL
        )
    ),
    contenido_json TEXT NOT NULL CHECK (json_valid(contenido_json)),
    PRIMARY KEY (id_rele, registro)
)
"""

ACTUALIZACION_REGISTROS_RELES_TABLE_SQL = """
CREATE TABLE actualizacion_registros_reles (
    id_rele INTEGER PRIMARY KEY REFERENCES reles(id),
    actualizado_en TEXT CHECK (
        actualizado_en IS NULL
        OR (
            length(actualizado_en) = 24
            AND actualizado_en GLOB '????-??-??T??:??:??.???Z'
            AND datetime(actualizado_en) IS NOT NULL
        )
    ),
    reintentar_en TEXT CHECK (
        reintentar_en IS NULL
        OR (
            length(reintentar_en) = 24
            AND reintentar_en GLOB '????-??-??T??:??:??.???Z'
            AND datetime(reintentar_en) IS NOT NULL
        )
    ),
    error TEXT
)
"""

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
    descripcion TEXT NOT NULL CHECK (length(trim(descripcion)) > 0),
    producto TEXT CHECK (producto IS NULL OR length(trim(producto)) > 0),
    formato_fecha INTEGER CHECK (formato_fecha IN (0, 1)),
    fase_tc_primario INTEGER CHECK (fase_tc_primario > 0),
    fase_tc_secundario INTEGER CHECK (fase_tc_secundario > 0),
    tierra_tc_primario INTEGER CHECK (tierra_tc_primario > 0),
    tierra_tc_secundario INTEGER CHECK (tierra_tc_secundario > 0),
    fase_relacion_interna INTEGER CHECK (fase_relacion_interna > 0),
    tierra_relacion_interna INTEGER CHECK (tierra_relacion_interna > 0),
    frecuencia_nominal INTEGER CHECK (frecuencia_nominal IN (50, 60)),
    CHECK (
        (
            producto IS NULL
            AND fase_tc_primario IS NULL
            AND fase_tc_secundario IS NULL
            AND tierra_tc_primario IS NULL
            AND tierra_tc_secundario IS NULL
            AND fase_relacion_interna IS NULL
            AND tierra_relacion_interna IS NULL
        )
        OR
        (
            producto IS NOT NULL
            AND fase_tc_primario IS NOT NULL
            AND fase_tc_secundario IS NOT NULL
            AND tierra_tc_primario IS NOT NULL
            AND tierra_tc_secundario IS NOT NULL
            AND fase_relacion_interna IS NOT NULL
            AND tierra_relacion_interna IS NOT NULL
        )
    )
);

{FALLAS_RELES_TABLE_SQL};

{OSCILOPERTURBOGRAMAS_TABLE_SQL};

{ACTUALIZACION_REGISTROS_RELES_TABLE_SQL};

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
