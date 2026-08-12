import sqlite3

from logosaurio import logger

from .dao_base import get_db_connection


class RelesDAO:
    def get_rele_description(self, id_modbus: int) -> str | None:
        conn = get_db_connection()
        try:
            row = conn.execute(
                "SELECT descripcion FROM reles WHERE id_modbus = ?",
                (id_modbus,),
            ).fetchone()
            return str(row["descripcion"]) if row else None
        except sqlite3.Error as exc:
            self._raise_query_error(f"descripcion del rele Modbus {id_modbus}", exc)
        finally:
            conn.close()

    def get_internal_id_by_modbus_id(self, id_modbus: int) -> int | None:
        conn = get_db_connection()
        try:
            row = conn.execute(
                "SELECT id FROM reles WHERE id_modbus = ?",
                (id_modbus,),
            ).fetchone()
            return int(row["id"]) if row else None
        except sqlite3.Error as exc:
            self._raise_query_error(f"ID interno del rele Modbus {id_modbus}", exc)
        finally:
            conn.close()

    def get_all_reles_with_descriptions(self) -> dict[int, str]:
        conn = get_db_connection()
        try:
            rows = conn.execute(
                """
                SELECT id_modbus, descripcion
                FROM reles
                WHERE UPPER(descripcion) NOT LIKE 'NO APLICA%'
                ORDER BY id_modbus
                """
            ).fetchall()
            return {
                int(row["id_modbus"]): str(row["descripcion"])
                for row in rows
            }
        except sqlite3.Error as exc:
            self._raise_query_error("catalogo de reles", exc)
        finally:
            conn.close()

    @staticmethod
    def _raise_query_error(operation: str, exc: sqlite3.Error):
        logger.error(
            "No se pudo consultar %s: %s",
            operation,
            exc,
            origin="MODBUS/DAO",
        )
        raise RuntimeError(f"Fallo al consultar {operation}") from exc


reles_dao = RelesDAO()
