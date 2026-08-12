import sqlite3

from logosaurio import logger

from .dao_base import get_db_connection


class GrdStateDAO:
    def record_transition(self, grd_id: int, timestamp: str, connected: int) -> None:
        """Persiste historico y estado vigente en una sola transaccion."""
        if connected not in (0, 1):
            raise ValueError(f"Estado conectado invalido para GRD {grd_id}: {connected}")

        conn = get_db_connection()
        try:
            conn.execute("BEGIN IMMEDIATE;")
            conn.execute(
                """
                INSERT INTO historicos (id_grd, timestamp, conectado)
                VALUES (?, ?, ?)
                """,
                (grd_id, timestamp, connected),
            )
            conn.execute(
                """
                INSERT INTO grd_estado_actual (id_grd, timestamp, conectado)
                VALUES (?, ?, ?)
                ON CONFLICT(id_grd) DO UPDATE SET
                    timestamp = excluded.timestamp,
                    conectado = excluded.conectado
                """,
                (grd_id, timestamp, connected),
            )
            conn.commit()
        except sqlite3.Error as exc:
            conn.rollback()
            logger.error(
                "No se pudo persistir la transicion de GRD %s en %s: %s",
                grd_id,
                timestamp,
                exc,
                origin="MODBUS/DAO",
            )
            raise RuntimeError(
                f"Fallo al persistir la transicion del GRD {grd_id} en {timestamp}"
            ) from exc
        finally:
            conn.close()

    def get_current_states(self) -> dict[int, int]:
        return {
            int(row["id_grd"]): int(row["conectado"])
            for row in self.get_operational_snapshot()
            if row["conectado"] is not None
        }

    def get_operational_snapshot(self) -> list[dict]:
        conn = get_db_connection()
        try:
            rows = conn.execute(
                """
                SELECT
                    g.id AS id_grd,
                    e.timestamp,
                    e.conectado,
                    g.descripcion
                FROM grd g
                LEFT JOIN grd_estado_actual e ON e.id_grd = g.id
                WHERE g.activo = 1
                  AND g.descripcion <> 'reserva'
                  AND g.descripcion <> 'SE - CD45 Murchison'
                ORDER BY g.id
                """
            ).fetchall()
            return [dict(row) for row in rows]
        except sqlite3.Error as exc:
            logger.error(
                "No se pudo obtener el estado operativo vigente de los GRD: %s",
                exc,
                origin="MODBUS/DAO",
            )
            raise RuntimeError("Fallo al consultar el estado operativo vigente de los GRD") from exc
        finally:
            conn.close()


grd_state_dao = GrdStateDAO()
