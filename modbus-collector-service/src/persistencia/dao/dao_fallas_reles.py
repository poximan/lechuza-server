import sqlite3

from logosaurio import logger

from .dao_base import get_db_connection


class FallasRelesDAO:
    def replace_if_newer(
        self,
        id_rele: int,
        numero_falla: int,
        timestamp: str,
        formato_timestamp: str,
        fasea_corr: int | None,
        faseb_corr: int | None,
        fasec_corr: int | None,
        tierra_corr: int | None,
    ) -> bool:
        if not timestamp:
            raise ValueError("Una falla de rele requiere timestamp valido")
        if formato_timestamp not in {"private", "iec870"}:
            raise ValueError(
                f"Formato de timestamp de falla invalido: {formato_timestamp}"
            )

        conn = get_db_connection()
        try:
            conn.execute("BEGIN IMMEDIATE;")
            result = conn.execute(
                """
                INSERT INTO fallas_reles (
                    id_rele, numero_falla, timestamp, formato_timestamp,
                    fasea_corr, faseb_corr, fasec_corr, tierra_corr
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id_rele) DO UPDATE SET
                    numero_falla = excluded.numero_falla,
                    timestamp = excluded.timestamp,
                    formato_timestamp = excluded.formato_timestamp,
                    fasea_corr = excluded.fasea_corr,
                    faseb_corr = excluded.faseb_corr,
                    fasec_corr = excluded.fasec_corr,
                    tierra_corr = excluded.tierra_corr
                WHERE excluded.numero_falla > fallas_reles.numero_falla
                   OR (
                       excluded.numero_falla = fallas_reles.numero_falla
                       AND excluded.timestamp > fallas_reles.timestamp
                   )
                """,
                (
                    id_rele,
                    numero_falla,
                    timestamp,
                    formato_timestamp,
                    fasea_corr,
                    faseb_corr,
                    fasec_corr,
                    tierra_corr,
                ),
            )
            conn.commit()
            return result.rowcount == 1
        except sqlite3.Error as exc:
            conn.rollback()
            logger.error(
                "No se pudo actualizar la falla %s del rele %s: %s",
                numero_falla,
                id_rele,
                exc,
                origin="MODBUS/DAO",
            )
            raise RuntimeError(
                f"Fallo al actualizar la falla {numero_falla} del rele {id_rele}"
            ) from exc
        finally:
            conn.close()

    def get_current_falla_for_rele(self, id_rele: int) -> dict | None:
        conn = get_db_connection()
        try:
            row = conn.execute(
                """
                SELECT id_rele, numero_falla, timestamp, formato_timestamp,
                       fasea_corr, faseb_corr, fasec_corr, tierra_corr
                FROM fallas_reles
                WHERE id_rele = ?
                """,
                (id_rele,),
            ).fetchone()
            return dict(row) if row else None
        except sqlite3.Error as exc:
            logger.error(
                "No se pudo consultar la ultima falla del rele %s: %s",
                id_rele,
                exc,
                origin="MODBUS/DAO",
            )
            raise RuntimeError(f"Fallo al consultar la ultima falla del rele {id_rele}") from exc
        finally:
            conn.close()


fallas_reles_dao = FallasRelesDAO()
