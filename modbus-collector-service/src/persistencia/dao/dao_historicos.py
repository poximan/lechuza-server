import math
import sqlite3
from datetime import datetime, timedelta

import pandas as pd
from logosaurio import logger

from src.utils import timebox

from .dao_base import get_db_connection


class HistoricosDAO:
    def get_connected_state_before_timestamp(self, grd_id: int, timestamp: datetime):
        conn = get_db_connection()
        try:
            row = conn.execute(
                """
                SELECT conectado
                FROM historicos
                WHERE id_grd = ? AND timestamp < ?
                ORDER BY timestamp DESC
                LIMIT 1
                """,
                (grd_id, timebox.utc_iso(timestamp)),
            ).fetchone()
            return int(row["conectado"]) if row else None
        except sqlite3.Error as exc:
            self._raise_query_error(
                f"estado anterior del GRD {grd_id} antes de {timestamp}",
                exc,
            )
        finally:
            conn.close()

    def get_latest_outages_for_grd(self, grd_id: int, limit_count: int = 10) -> list[dict]:
        if limit_count <= 0:
            return []

        conn = get_db_connection()
        try:
            rows = conn.execute(
                """
                WITH ordered AS (
                    SELECT
                        timestamp,
                        conectado,
                        LAG(conectado) OVER (ORDER BY timestamp) AS prev_conectado,
                        LEAD(conectado) OVER (ORDER BY timestamp) AS next_conectado,
                        LEAD(timestamp) OVER (ORDER BY timestamp) AS next_timestamp
                    FROM historicos
                    WHERE id_grd = ?
                )
                SELECT
                    timestamp AS start_timestamp,
                    CASE WHEN next_conectado = 1 THEN next_timestamp ELSE NULL END AS end_timestamp
                FROM ordered
                WHERE conectado = 0 AND prev_conectado = 1
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (grd_id, limit_count),
            ).fetchall()
            return [dict(row) for row in rows]
        except sqlite3.Error as exc:
            self._raise_query_error(f"ultimas caidas del GRD {grd_id}", exc)
        finally:
            conn.close()

    def get_weekly_data_for_grd(
        self,
        grd_id: int,
        reference_date_str: str,
        page_number: int = 0,
    ) -> pd.DataFrame:
        reference_date = timebox.parse_format(reference_date_str, "%Y-%m-%d")
        week_end = reference_date - timedelta(weeks=page_number)
        week_start = week_end - timedelta(days=6)
        range_end = (
            timebox.utc_now()
            if page_number == 0
            else week_end + timedelta(days=1)
        )
        return self._read_frame(
            """
            SELECT timestamp, id_grd, conectado
            FROM historicos
            WHERE id_grd = ? AND timestamp >= ? AND timestamp < ?
            ORDER BY timestamp ASC
            """,
            (
                grd_id,
                timebox.utc_iso(week_start),
                timebox.utc_iso(range_end),
            ),
            f"datos semanales del GRD {grd_id}",
        )

    def get_data_for_grd_range(
        self,
        grd_id: int,
        range_start: datetime,
        range_end: datetime,
    ) -> pd.DataFrame:
        return self._read_frame(
            """
            SELECT timestamp, id_grd, conectado
            FROM historicos
            WHERE id_grd = ? AND timestamp >= ? AND timestamp < ?
            ORDER BY timestamp ASC
            """,
            (
                grd_id,
                timebox.utc_iso(range_start),
                timebox.utc_iso(range_end),
            ),
            f"datos del GRD {grd_id} entre {range_start} y {range_end}",
        )

    def get_data_page_for_grd(
        self,
        grd_id: int,
        page_number: int,
        page_size: int,
    ) -> tuple[pd.DataFrame, int]:
        conn = get_db_connection()
        try:
            total = int(
                conn.execute(
                    "SELECT COUNT(1) AS total FROM historicos WHERE id_grd = ?",
                    (grd_id,),
                ).fetchone()["total"]
            )
            frame = pd.read_sql_query(
                """
                SELECT timestamp, id_grd, conectado
                FROM historicos
                WHERE id_grd = ?
                ORDER BY timestamp DESC
                LIMIT ? OFFSET ?
                """,
                conn,
                params=(grd_id, page_size, max(0, page_number) * page_size),
            )
            if not frame.empty:
                frame["timestamp"] = timebox.utc_series(frame["timestamp"])
                frame = frame.sort_values(by="timestamp").reset_index(drop=True)
            return frame, total
        except (sqlite3.Error, pd.errors.DatabaseError, ValueError) as exc:
            self._raise_query_error(f"pagina historica del GRD {grd_id}", exc)
        finally:
            conn.close()

    def get_total_weeks_for_grd(self, grd_id: int, _reference_date_str: str) -> int:
        minimum = self._get_minimum_timestamp(grd_id)
        if minimum is None:
            return 0
        current = timebox.utc_now()
        if current.date() < minimum.date():
            return 0
        return ((current.date() - minimum.date()).days // 7) + 1

    def get_total_thirty_day_periods_for_grd(self, grd_id: int) -> int:
        minimum = self._get_minimum_timestamp(grd_id)
        if minimum is None:
            return 0
        current = timebox.utc_now()
        if minimum > current:
            return 0
        seconds = (current - minimum).total_seconds()
        period_seconds = timedelta(days=30).total_seconds()
        return max(1, math.ceil(seconds / period_seconds))

    def _get_minimum_timestamp(self, grd_id: int) -> datetime | None:
        conn = get_db_connection()
        try:
            row = conn.execute(
                "SELECT MIN(timestamp) AS min_timestamp FROM historicos WHERE id_grd = ?",
                (grd_id,),
            ).fetchone()
            value = row["min_timestamp"] if row else None
            return timebox.parse(value, legacy=True) if value else None
        except (sqlite3.Error, pd.errors.DatabaseError, ValueError) as exc:
            self._raise_query_error(f"primer historico del GRD {grd_id}", exc)
        finally:
            conn.close()

    def _read_frame(self, query: str, params: tuple, operation: str) -> pd.DataFrame:
        conn = get_db_connection()
        try:
            frame = pd.read_sql_query(query, conn, params=params)
            if not frame.empty:
                frame["timestamp"] = timebox.utc_series(frame["timestamp"])
            return frame
        except (sqlite3.Error, pd.errors.DatabaseError, ValueError) as exc:
            self._raise_query_error(operation, exc)
        finally:
            conn.close()

    @staticmethod
    def _raise_query_error(operation: str, exc: Exception):
        logger.error(
            "No se pudo consultar %s: %s",
            operation,
            exc,
            origin="MODBUS/DAO",
        )
        raise RuntimeError(f"Fallo al consultar {operation}") from exc


historicos_dao = HistoricosDAO()
