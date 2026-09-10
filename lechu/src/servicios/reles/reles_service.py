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

    def get_disturbances(self, relay_id: int) -> dict[str, Any]:
        if relay_id < 1 or relay_id > 255:
            raise ValueError(f"ID Modbus de rele fuera de rango: {relay_id}")
        return self.modbus_client.get_rele_disturbances(relay_id)

    def get_disturbance(self, relay_id: int, record_number: int) -> dict[str, Any]:
        if not 1 <= relay_id <= 255 or not 1 <= record_number <= 5:
            raise ValueError("Rele o registro fuera de rango")
        return self.modbus_client.get_rele_disturbance(relay_id, record_number)

    def read_clock(self, relay_id: int) -> dict[str, Any]:
        if relay_id < 1 or relay_id > 255:
            raise ValueError(f"ID Modbus de rele fuera de rango: {relay_id}")
        return self.modbus_client.read_rele_clock(relay_id)
