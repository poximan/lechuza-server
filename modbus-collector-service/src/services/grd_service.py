from __future__ import annotations

from typing import Any

from src import config
from src.control.latest_state_registry import LatestStateRegistry
from src.persistencia.dao.dao_estado_grd import GrdStateDAO
from src.persistencia.dao.dao_grd import GrdDAO
from src.utils import timebox


class GrdService:
    def __init__(
        self,
        grd_dao: GrdDAO,
        state_dao: GrdStateDAO,
        state_registry: LatestStateRegistry,
    ) -> None:
        self._grd_dao = grd_dao
        self._state_dao = state_dao
        self._state_registry = state_registry

    def descriptions(self) -> dict[int, str]:
        return self._grd_dao.get_all_grds_with_descriptions()

    def summary(self) -> dict[str, Any]:
        rows = self._state_dao.get_operational_snapshot()
        states = {
            int(row["id_grd"]): int(row["conectado"])
            for row in rows
            if row["conectado"] is not None
        }
        descriptions = {
            int(row["id_grd"]): str(row["descripcion"])
            for row in rows
        }
        total = len(states)
        connected = sum(1 for value in states.values() if value == 1)
        unavailable = self._serialize_unavailable(descriptions, states)
        return {
            "summary": {
                "porcentaje": round((connected * 100.0 / total), 2) if total else 0.0,
                "total": total,
                "conectados": connected,
                "no_disponibles": len(unavailable),
                "ts": timebox.utc_iso(),
            },
            "states": states,
            "disconnected": [
                {
                    "id_grd": int(row["id_grd"]),
                    "description": str(row["descripcion"]),
                    "last_disconnected_timestamp": self._timestamp_iso(row["timestamp"]),
                }
                for row in rows
                if row["conectado"] == 0
            ],
            "unavailable": unavailable,
        }

    def _serialize_unavailable(
        self,
        descriptions: dict[int, str],
        states: dict[int, int],
    ) -> list[dict]:
        result = {
            grd_id: {
                "id_grd": grd_id,
                "description": description,
                "consecutive_failures": 0,
                "confirmable_failures": 0,
                "failure_threshold": config.GRD_FAILURE_THRESHOLD,
                "disconnect_confirmed": False,
                "reason": "sin_estado_confirmado",
                "since": "",
            }
            for grd_id, description in descriptions.items()
            if grd_id not in states
        }
        for grd_id, details in self._state_registry.unavailable_snapshot().items():
            confirmable_failures = int(details["confirmable_failures"])
            result[grd_id] = {
                "id_grd": grd_id,
                "description": descriptions.get(grd_id, "GRD desconocido"),
                "consecutive_failures": int(details["consecutive_failures"]),
                "confirmable_failures": confirmable_failures,
                "failure_threshold": config.GRD_FAILURE_THRESHOLD,
                "disconnect_confirmed": (
                    confirmable_failures >= config.GRD_FAILURE_THRESHOLD
                ),
                "reason": str(details["reason"]),
                "since": str(details["since"]),
            }
        return sorted(result.values(), key=lambda item: int(item["id_grd"]))

    @staticmethod
    def _timestamp_iso(value: Any) -> str:
        if not value:
            return ""
        parsed = timebox.parse(value, legacy=True) if isinstance(value, str) else value
        return timebox.utc_iso(parsed)
