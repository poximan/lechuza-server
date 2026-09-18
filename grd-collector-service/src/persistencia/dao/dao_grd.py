import sqlite3

from logosaurio import logger

from .dao_base import get_db_connection


class GrdDAO:
    def get_all_grds_with_descriptions(self, only_active: bool = False) -> dict[int, str]:
        conn = get_db_connection()
        try:
            query = "SELECT id, descripcion FROM grd WHERE descripcion <> 'reserva'"
            if only_active:
                query += " AND activo = 1"
            query += " ORDER BY id"
            rows = conn.execute(query).fetchall()
            return {int(row["id"]): str(row["descripcion"]) for row in rows}
        except sqlite3.Error as exc:
            self._raise_query_error("catalogo de GRD", exc)
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


grd_dao = GrdDAO()
