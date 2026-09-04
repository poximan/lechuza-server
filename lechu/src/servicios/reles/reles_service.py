from __future__ import annotations

from typing import Any


class RelesService:
    def __init__(self, modbus_client: Any):
        self.modbus_client = modbus_client

    def get_contract(self) -> dict[str, Any]:
        return {
            "observer_enabled": self.modbus_client.get_reles_observer(),
            "faults": self.modbus_client.get_reles_faults(),
        }

    def set_observer(self, enabled: bool) -> dict[str, bool]:
        return {"enabled": self.modbus_client.set_reles_observer(enabled)}

    def get_latest_disturbance(self, relay_id: int) -> dict[str, Any]:
        if relay_id < 0 or relay_id > 255:
            raise ValueError(f"ID Modbus de rele fuera de rango: {relay_id}")
        return self.modbus_client.get_rele_latest_disturbance(relay_id)

    def read_clock(self, relay_id: int) -> dict[str, Any]:
        if relay_id < 1 or relay_id > 255:
            raise ValueError(f"ID Modbus de rele fuera de rango: {relay_id}")
        return self.modbus_client.read_rele_clock(relay_id)
