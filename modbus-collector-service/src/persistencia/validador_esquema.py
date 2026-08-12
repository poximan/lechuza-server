from __future__ import annotations

import sqlite3

from src.persistencia.dao.dao_base import get_db_connection
from src.persistencia.ddl_esquema import SCHEMA_VERSION


EXPECTED_COLUMNS = {
    "grd": {"id", "descripcion", "activo"},
    "historicos": {"id_grd", "timestamp", "conectado"},
    "grd_estado_actual": {"id_grd", "timestamp", "conectado"},
    "reles": {"id", "id_modbus", "descripcion"},
    "fallas_reles": {
        "id",
        "id_rele",
        "numero_falla",
        "timestamp",
        "fasea_corr",
        "faseb_corr",
        "fasec_corr",
        "tierra_corr",
    },
}

EXPECTED_PRIMARY_KEYS = {
    "grd": ["id"],
    "historicos": ["id_grd", "timestamp"],
    "grd_estado_actual": ["id_grd"],
    "reles": ["id"],
    "fallas_reles": ["id"],
}

EXPECTED_NOT_NULL = {
    "grd": {"descripcion", "activo"},
    "historicos": {"id_grd", "timestamp", "conectado"},
    "grd_estado_actual": {"timestamp", "conectado"},
    "reles": {"id_modbus", "descripcion"},
    "fallas_reles": {"id_rele", "numero_falla", "timestamp"},
}

EXPECTED_FOREIGN_KEYS = {
    "grd": set(),
    "historicos": {("id_grd", "grd", "id")},
    "grd_estado_actual": {("id_grd", "grd", "id")},
    "reles": set(),
    "fallas_reles": {("id_rele", "reles", "id")},
}


class DatabaseContractError(RuntimeError):
    pass


def validate_database_schema(
    conn: sqlite3.Connection | None = None,
    *,
    require_operational_data: bool = True,
) -> None:
    """Valida version, tablas y clave critica sin modificar la base."""
    owns_connection = conn is None
    current = conn or get_db_connection()
    try:
        version = int(current.execute("PRAGMA user_version;").fetchone()[0])
        if version != SCHEMA_VERSION:
            raise DatabaseContractError(
                f"Version de esquema invalida: esperada={SCHEMA_VERSION}, encontrada={version}"
            )

        for table_name, expected in EXPECTED_COLUMNS.items():
            rows = current.execute(f"PRAGMA table_info({table_name});").fetchall()
            found = {str(row[1]) for row in rows}
            if found != expected:
                raise DatabaseContractError(
                    f"Contrato invalido para {table_name}: esperadas={sorted(expected)}, "
                    f"encontradas={sorted(found)}"
                )
            primary_key = [
                str(row[1])
                for row in sorted(rows, key=lambda row: int(row[5]))
                if int(row[5])
            ]
            if primary_key != EXPECTED_PRIMARY_KEYS[table_name]:
                raise DatabaseContractError(
                    f"Clave primaria invalida para {table_name}: {primary_key}"
                )
            not_null = {str(row[1]) for row in rows if int(row[3])}
            if not_null != EXPECTED_NOT_NULL[table_name]:
                raise DatabaseContractError(
                    f"Restricciones NOT NULL invalidas para {table_name}: "
                    f"{sorted(not_null)}"
                )

        for table_name, expected in EXPECTED_FOREIGN_KEYS.items():
            rows = current.execute(
                f"PRAGMA foreign_key_list({table_name});"
            ).fetchall()
            found = {
                (str(row[3]), str(row[2]), str(row[4]))
                for row in rows
            }
            if found != expected:
                raise DatabaseContractError(
                    f"Claves foraneas invalidas para {table_name}: {sorted(found)}"
                )

        history_sql_row = current.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'historicos'"
        ).fetchone()
        history_sql = str(history_sql_row[0]).upper() if history_sql_row else ""
        if "WITHOUT ROWID" not in history_sql:
            raise DatabaseContractError("historicos debe usar WITHOUT ROWID")

        relay_unique_contract = False
        for index_row in current.execute("PRAGMA index_list(reles);").fetchall():
            if not int(index_row[2]):
                continue
            index_name = str(index_row[1]).replace("'", "''")
            columns = [
                str(row[2])
                for row in current.execute(
                    f"PRAGMA index_info('{index_name}');"
                ).fetchall()
            ]
            if columns == ["id_modbus"]:
                relay_unique_contract = True
                break
        if not relay_unique_contract:
            raise DatabaseContractError(
                "reles debe garantizar unicidad sobre id_modbus"
            )

        explicit_indexes = current.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'index' AND sql IS NOT NULL
            ORDER BY name
            """
        ).fetchall()
        if explicit_indexes:
            raise DatabaseContractError(
                "El esquema contiene indices no declarados por contrato: "
                f"{[str(row[0]) for row in explicit_indexes]}"
            )

        foreign_key_errors = current.execute("PRAGMA foreign_key_check;").fetchall()
        if foreign_key_errors:
            raise DatabaseContractError(
                f"La base contiene {len(foreign_key_errors)} violaciones de claves foraneas"
            )

        grd_count = int(current.execute("SELECT COUNT(1) FROM grd").fetchone()[0])
        if require_operational_data and grd_count == 0:
            raise DatabaseContractError(
                "El catalogo GRD esta vacio; cargue los datos operativos antes de iniciar"
            )
    finally:
        if owns_connection:
            current.close()


def check_database_access() -> None:
    conn = get_db_connection()
    try:
        conn.execute("SELECT 1 FROM grd LIMIT 1;").fetchone()
        conn.execute("SELECT 1 FROM grd_estado_actual LIMIT 1;").fetchone()
    finally:
        conn.close()
