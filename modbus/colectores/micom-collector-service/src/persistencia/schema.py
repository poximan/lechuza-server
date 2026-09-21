from __future__ import annotations

import os
import sqlite3
import tempfile

from .configuracion_base_datos import DATABASE_FILE


SCHEMA_VERSION = 1
SCHEMA_SQL = """
PRAGMA foreign_keys = ON;
BEGIN IMMEDIATE;
CREATE TABLE reles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    id_modbus INTEGER NOT NULL UNIQUE,
    descripcion TEXT NOT NULL CHECK (length(trim(descripcion)) > 0),
    producto TEXT,
    formato_fecha INTEGER CHECK (formato_fecha IN (0, 1)),
    fase_tc_primario INTEGER CHECK (fase_tc_primario > 0),
    fase_tc_secundario INTEGER CHECK (fase_tc_secundario > 0),
    tierra_tc_primario INTEGER CHECK (tierra_tc_primario > 0),
    tierra_tc_secundario INTEGER CHECK (tierra_tc_secundario > 0),
    fase_relacion_interna INTEGER CHECK (fase_relacion_interna > 0),
    tierra_relacion_interna INTEGER CHECK (tierra_relacion_interna > 0),
    frecuencia_nominal INTEGER CHECK (frecuencia_nominal IN (50, 60))
);
CREATE TABLE fallas_reles (
    id_rele INTEGER PRIMARY KEY NOT NULL,
    numero_falla INTEGER NOT NULL,
    timestamp TEXT NOT NULL CHECK (
        length(timestamp) = 24
        AND timestamp GLOB '????-??-??T??:??:??.???Z'
        AND datetime(timestamp) IS NOT NULL
    ),
    formato_timestamp TEXT NOT NULL CHECK (formato_timestamp IN ('private', 'iec870')),
    fasea_corr INTEGER,
    faseb_corr INTEGER,
    fasec_corr INTEGER,
    tierra_corr INTEGER,
    FOREIGN KEY (id_rele) REFERENCES reles(id)
);
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
);
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
);
PRAGMA user_version = 1;
COMMIT;
"""
EXPECTED_COLUMNS = {
    "reles": {
        "id", "id_modbus", "descripcion", "producto", "formato_fecha",
        "fase_tc_primario", "fase_tc_secundario", "tierra_tc_primario",
        "tierra_tc_secundario", "fase_relacion_interna",
        "tierra_relacion_interna", "frecuencia_nominal",
    },
    "fallas_reles": {
        "id_rele", "numero_falla", "timestamp", "formato_timestamp",
        "fasea_corr", "faseb_corr", "fasec_corr", "tierra_corr",
    },
    "osciloperturbogramas_reles": {
        "id_rele", "registro", "timestamp", "descargado_en", "contenido_json",
    },
    "actualizacion_registros_reles": {
        "id_rele", "actualizado_en", "reintentar_en", "error",
    },
}
EXPECTED_PRIMARY_KEYS = {
    "reles": ["id"],
    "fallas_reles": ["id_rele"],
    "osciloperturbogramas_reles": ["id_rele", "registro"],
    "actualizacion_registros_reles": ["id_rele"],
}
EXPECTED_FOREIGN_KEYS = {
    "reles": set(),
    "fallas_reles": {("id_rele", "reles", "id")},
    "osciloperturbogramas_reles": {("id_rele", "reles", "id")},
    "actualizacion_registros_reles": {("id_rele", "reles", "id")},
}
EXPECTED_NOT_NULL = {
    "reles": {"id_modbus", "descripcion"},
    "fallas_reles": {
        "id_rele", "numero_falla", "timestamp", "formato_timestamp",
    },
    "osciloperturbogramas_reles": {
        "id_rele", "registro", "timestamp", "contenido_json",
    },
    "actualizacion_registros_reles": set(),
}


def ensure_database() -> None:
    if not os.path.isfile(DATABASE_FILE):
        os.makedirs(os.path.dirname(DATABASE_FILE), exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(
            prefix="micom-schema-",
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
                f"Version MiCOM invalida: esperada={SCHEMA_VERSION}, encontrada={version}"
            )
        for table, expected in EXPECTED_COLUMNS.items():
            rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
            found = {str(row[1]) for row in rows}
            if found != expected:
                raise RuntimeError(
                    f"Contrato MiCOM invalido en {table}: {sorted(found)}"
                )
            primary_key = [
                str(row[1])
                for row in sorted(rows, key=lambda row: int(row[5]))
                if int(row[5])
            ]
            if primary_key != EXPECTED_PRIMARY_KEYS[table]:
                raise RuntimeError(f"Clave primaria MiCOM invalida en {table}")
            not_null = {str(row[1]) for row in rows if int(row[3])}
            if not_null != EXPECTED_NOT_NULL[table]:
                raise RuntimeError(f"Restricciones MiCOM invalidas en {table}")
            foreign_keys = {
                (str(row[3]), str(row[2]), str(row[4]))
                for row in conn.execute(f"PRAGMA foreign_key_list({table})").fetchall()
            }
            if foreign_keys != EXPECTED_FOREIGN_KEYS[table]:
                raise RuntimeError(f"Claves foraneas MiCOM invalidas en {table}")
        integrity = conn.execute("PRAGMA integrity_check").fetchone()
        if not integrity or integrity[0] != "ok":
            raise RuntimeError(f"Integridad MiCOM invalida: {integrity}")
        if conn.execute("PRAGMA foreign_key_check").fetchall():
            raise RuntimeError("La base MiCOM viola claves foraneas")
        unique_modbus_id = any(
            int(index[2])
            and [
                str(row[2])
                for row in conn.execute(
                    f"PRAGMA index_info('{str(index[1]).replace(chr(39), chr(39) * 2)}')"
                ).fetchall()
            ] == ["id_modbus"]
            for index in conn.execute("PRAGMA index_list(reles)").fetchall()
        )
        if not unique_modbus_id:
            raise RuntimeError("reles debe garantizar unicidad sobre id_modbus")
