from __future__ import annotations

from typing import Any

import config
from src.utils import timebox


class ExemysService:
    def __init__(self, modbus_client: Any, modem_client: Any):
        self.modbus_client = modbus_client
        self.modem_client = modem_client

    def get_contract(self) -> dict[str, Any]:
        try:
            modem = self.modem_client.get_status()
        except Exception as exc:
            modem = {
                "ip": None,
                "port": None,
                "state": "desconocido",
                "error": f"{type(exc).__name__}: {exc}",
            }
        return {
            "reference_now": timebox.utc_iso(),
            "summary": self.modbus_client.get_summary(),
            "descriptions": self.modbus_client.get_descriptions(),
            "modem": modem,
            "thresholds": {
                "red_below": config.GLOBAL_THRESHOLD_ROJO,
                "yellow_below": config.GLOBAL_THRESHOLD_AMARILLO,
            },
            "links": {
                "external_check": config.MODEM_EXTERNAL_CHECK_URL,
                "modem_admin": config.MODEM_ADMIN_URL,
            },
        }

    def get_grd_detail(self, grd_id: int, window: str, page: int) -> dict[str, Any]:
        if window not in {"1sem", "1mes", "todo"}:
            raise ValueError("window fuera de contrato")
        if page < 0:
            raise ValueError("page fuera de contrato")
        descriptions = self.modbus_client.get_descriptions()
        if grd_id not in descriptions:
            raise ValueError(f"GRD {grd_id} no existe en el catalogo")
        return {
            "grd_id": grd_id,
            "description": descriptions[grd_id],
            "window": window,
            "page": page,
            "history": self.modbus_client.get_history(grd_id, window, page),
            "outages": self.modbus_client.get_outages(grd_id, limit=10),
        }
