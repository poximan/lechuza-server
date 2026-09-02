import sqlite3

from logosaurio import logger

from .dao_base import get_db_connection


class RelesDAO:
    METADATA_COLUMNS = """
        id, id_modbus, descripcion, producto, formato_fecha,
        fase_tc_primario, fase_tc_secundario,
        tierra_tc_primario, tierra_tc_secundario,
        fase_relacion_interna, tierra_relacion_interna,
        frecuencia_nominal
    """

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

    def get_all_relay_metadata(self) -> dict[int, dict]:
        conn = get_db_connection()
        try:
            rows = conn.execute(
                f"""
                SELECT {self.METADATA_COLUMNS}
                FROM reles
                WHERE UPPER(descripcion) NOT LIKE 'NO APLICA%'
                ORDER BY id_modbus
                """
            ).fetchall()
            return {int(row["id_modbus"]): dict(row) for row in rows}
        except sqlite3.Error as exc:
            self._raise_query_error("metadatos de reles", exc)
        finally:
            conn.close()

    def get_relay_metadata(self, id_modbus: int) -> dict | None:
        conn = get_db_connection()
        try:
            row = conn.execute(
                f"SELECT {self.METADATA_COLUMNS} FROM reles WHERE id_modbus = ?",
                (id_modbus,),
            ).fetchone()
            return dict(row) if row else None
        except sqlite3.Error as exc:
            self._raise_query_error(f"metadatos del rele Modbus {id_modbus}", exc)
        finally:
            conn.close()

    def save_date_format(self, id_modbus: int, date_format: int) -> None:
        if date_format not in {0, 1}:
            raise ValueError(f"Formato de fecha MiCOM invalido: {date_format}")
        self._update_metadata(
            id_modbus,
            "formato_fecha = ?",
            (date_format,),
            "formato de fecha",
        )

    def save_current_profile(
        self,
        id_modbus: int,
        *,
        product: str,
        phase_primary_ct: int,
        phase_secondary_ct: int,
        earth_primary_ct: int,
        earth_secondary_ct: int,
        phase_internal_ratio: int,
        earth_internal_ratio: int,
    ) -> None:
        values = (
            product,
            phase_primary_ct,
            phase_secondary_ct,
            earth_primary_ct,
            earth_secondary_ct,
            phase_internal_ratio,
            earth_internal_ratio,
        )
        if not product.strip() or any(value <= 0 for value in values[1:]):
            raise ValueError("Perfil de corriente MiCOM invalido")
        self._update_metadata(
            id_modbus,
            """
            producto = ?, fase_tc_primario = ?, fase_tc_secundario = ?,
            tierra_tc_primario = ?, tierra_tc_secundario = ?,
            fase_relacion_interna = ?, tierra_relacion_interna = ?
            """,
            values,
            "perfil de corriente",
        )

    def save_nominal_frequency(self, id_modbus: int, frequency: int) -> None:
        if frequency not in {50, 60}:
            raise ValueError(f"Frecuencia nominal MiCOM invalida: {frequency}")
        self._update_metadata(
            id_modbus,
            "frecuencia_nominal = ?",
            (frequency,),
            "frecuencia nominal",
        )

    def _update_metadata(
        self,
        id_modbus: int,
        assignments: str,
        values: tuple,
        operation: str,
    ) -> None:
        conn = get_db_connection()
        try:
            result = conn.execute(
                f"UPDATE reles SET {assignments} WHERE id_modbus = ?",
                (*values, id_modbus),
            )
            if result.rowcount != 1:
                raise RuntimeError(
                    f"No existe el rele Modbus {id_modbus} para guardar {operation}"
                )
            conn.commit()
        except sqlite3.Error as exc:
            conn.rollback()
            self._raise_query_error(f"actualizacion de {operation}", exc)
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
