import sqlite3

from logosaurio import logger

from .dao_base import get_db_connection


class FallasRelesDAO:
    def insert_if_absent(
        self,
        id_rele: int,
        numero_falla: int,
        timestamp: str,
        fasea_corr: int | None,
        faseb_corr: int | None,
        fasec_corr: int | None,
        tierra_corr: int | None,
    ) -> bool:
        if not timestamp:
            raise ValueError("Una falla de rele requiere timestamp valido")

        conn = get_db_connection()
        try:
            conn.execute("BEGIN IMMEDIATE;")
            exists = conn.execute(
                """
                SELECT 1
                FROM fallas_reles
                WHERE id_rele = ? AND numero_falla = ? AND timestamp = ?
                """,
                (id_rele, numero_falla, timestamp),
            ).fetchone()
            if exists:
                conn.rollback()
                return False

            conn.execute(
                """
                INSERT INTO fallas_reles (
                    id_rele, numero_falla, timestamp,
                    fasea_corr, faseb_corr, fasec_corr, tierra_corr
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    id_rele,
                    numero_falla,
                    timestamp,
                    fasea_corr,
                    faseb_corr,
                    fasec_corr,
                    tierra_corr,
                ),
            )
            conn.commit()
            return True
        except sqlite3.Error as exc:
            conn.rollback()
            logger.error(
                "No se pudo insertar la falla %s del rele %s: %s",
                numero_falla,
                id_rele,
                exc,
                origin="MODBUS/DAO",
            )
            raise RuntimeError(
                f"Fallo al persistir la falla {numero_falla} del rele {id_rele}"
            ) from exc
        finally:
            conn.close()

    def get_latest_falla_for_rele(self, id_rele: int) -> dict | None:
        conn = get_db_connection()
        try:
            row = conn.execute(
                """
                SELECT id_rele, numero_falla, timestamp,
                       fasea_corr, faseb_corr, fasec_corr, tierra_corr
                FROM fallas_reles
                WHERE id_rele = ?
                ORDER BY timestamp DESC, id DESC
                LIMIT 1
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
