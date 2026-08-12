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
