import json
from contextlib import closing
from datetime import timedelta
from typing import Any

from .dao_base import get_db_connection
from src.utils import timebox


class OsciloperturbogramasRelesDAO:
    """Conserva los registros disponibles del rele y el estado de su descarga."""

    REFRESH_INTERVAL = timedelta(days=30)
    RETRY_INTERVAL = timedelta(minutes=30)

    @staticmethod
    def _utc_timestamp(value: Any, field: str) -> str:
        if not isinstance(value, str) or not value.endswith("Z"):
            raise ValueError(f"{field} debe ser una estampa UTC")
        normalized = timebox.utc_iso_milliseconds(
            timebox.parse_preserving_subseconds(value)
        )
        if normalized != value:
            raise ValueError(f"{field} debe usar milisegundos UTC")
        return normalized

    def state(self, relay_id: int) -> dict[str, Any]:
        with closing(get_db_connection()) as conn:
            row = conn.execute(
                """
                SELECT actualizado_en, reintentar_en, error
                FROM actualizacion_registros_reles
                WHERE id_rele = ?
                """,
                (relay_id,),
            ).fetchone()
            return dict(row) if row else {
                "actualizado_en": None,
                "reintentar_en": None,
                "error": None,
            }

    def next_refresh(self, relay_id: int):
        state = self.state(relay_id)
        if state["reintentar_en"]:
            return timebox.parse(state["reintentar_en"])
        if state["actualizado_en"]:
            return timebox.parse(state["actualizado_en"]) + self.REFRESH_INTERVAL
        return timebox.utc_now()

    def list_records(self, relay_id: int) -> dict[str, Any]:
        with closing(get_db_connection()) as conn:
            rows = conn.execute(
                """
                SELECT registro AS record_number, timestamp,
                       descargado_en AS downloaded_at
                FROM osciloperturbogramas_reles
                WHERE id_rele = ?
                ORDER BY timestamp DESC, registro
                """,
                (relay_id,),
            ).fetchall()
        state = self.state(relay_id)
        if rows:
            if state["error"]:
                inventory_status = "partial"
            elif state["actualizado_en"]:
                inventory_status = "available"
            else:
                inventory_status = "collecting"
        elif state["error"]:
            inventory_status = "error"
        elif state["actualizado_en"]:
            inventory_status = "confirmed_empty"
        else:
            inventory_status = "pending"
        return {
            "items": [dict(row) for row in rows],
            "inventory_status": inventory_status,
            "refresh": {
                "last_completed_at": state["actualizado_en"],
                "retry_at": state["reintentar_en"],
                "error": state["error"],
            },
            "next_refresh_timestamp": timebox.utc_iso_milliseconds(
                self.next_refresh(relay_id)
            ),
        }

    def get(self, relay_id: int, record_number: int) -> dict[str, Any] | None:
        if not 1 <= record_number <= 5:
            raise ValueError("El registro debe estar entre 1 y 5")
        with closing(get_db_connection()) as conn:
            row = conn.execute(
                """
                SELECT timestamp, contenido_json, descargado_en
                FROM osciloperturbogramas_reles
                WHERE id_rele = ? AND registro = ?
                """,
                (relay_id, record_number),
            ).fetchone()
            if row is None:
                return None
            payload = json.loads(row["contenido_json"])
        if not isinstance(payload, dict):
            raise RuntimeError("El osciloperturbograma almacenado no es un objeto")
        metadata = payload.get("metadata")
        if (
            payload.get("record_number") != record_number
            or not isinstance(metadata, dict)
            or metadata.get("trigger_timestamp") != row["timestamp"]
        ):
            raise RuntimeError("El osciloperturbograma almacenado es inconsistente")
        payload["downloaded_at"] = row["descargado_en"]
        return payload

    def save(self, relay_id: int, payload: dict[str, Any]) -> None:
        if payload.get("status") != "available":
            raise ValueError("Solo se guarda un osciloperturbograma disponible")
        record_number = payload.get("record_number")
        if not isinstance(record_number, int) or not 1 <= record_number <= 5:
            raise ValueError("Numero de registro de osciloperturbograma invalido")
        metadata = payload.get("metadata")
        if not isinstance(metadata, dict):
            raise ValueError("Faltan metadatos del osciloperturbograma")
        timestamp = self._utc_timestamp(
            metadata.get("trigger_timestamp"),
            "metadata.trigger_timestamp",
        )
        now = timebox.utc_iso_milliseconds(timebox.utc_now())
        content = json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        )
        with closing(get_db_connection()) as conn, conn:
            conn.execute(
                """
                INSERT INTO osciloperturbogramas_reles
                    (id_rele, registro, timestamp, descargado_en, contenido_json)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(id_rele, registro) DO UPDATE SET
                    timestamp = excluded.timestamp,
                    descargado_en = excluded.descargado_en,
                    contenido_json = excluded.contenido_json
                """,
                (relay_id, record_number, timestamp, now, content),
            )

    def complete(self, relay_id: int, records: list[int]) -> None:
        if len(records) != len(set(records)) or any(
            not isinstance(record, int) or not 1 <= record <= 5
            for record in records
        ):
            raise ValueError("Directorio de osciloperturbogramas invalido")
        now = timebox.utc_iso_milliseconds(timebox.utc_now())
        with closing(get_db_connection()) as conn, conn:
            conn.execute(
                """
                INSERT INTO actualizacion_registros_reles
                    (id_rele, actualizado_en, reintentar_en, error)
                VALUES (?, ?, NULL, NULL)
                ON CONFLICT(id_rele) DO UPDATE SET
                    actualizado_en = excluded.actualizado_en,
                    reintentar_en = NULL,
                    error = NULL
                """,
                (relay_id, now),
            )

    def failed(
        self,
        relay_id: int,
        error: Exception,
        retry_interval: timedelta | None = None,
    ) -> None:
        interval = retry_interval or self.RETRY_INTERVAL
        if interval.total_seconds() <= 0:
            raise ValueError("El intervalo de reintento debe ser positivo")
        retry = timebox.utc_iso_milliseconds(timebox.utc_now() + interval)
        with closing(get_db_connection()) as conn, conn:
            conn.execute(
                """
                INSERT INTO actualizacion_registros_reles
                    (id_rele, actualizado_en, reintentar_en, error)
                VALUES (?, NULL, ?, ?)
                ON CONFLICT(id_rele) DO UPDATE SET
                    reintentar_en = excluded.reintentar_en,
                    error = excluded.error
                """,
                (relay_id, retry, str(error)),
            )


osciloperturbogramas_reles_dao = OsciloperturbogramasRelesDAO()
