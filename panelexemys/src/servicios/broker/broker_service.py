from __future__ import annotations

import threading
from typing import Any


class BrokerService:
    def __init__(self, mqtt_client_manager: Any):
        self.mqtt_client_manager = mqtt_client_manager

    def get_contract(self) -> dict[str, Any]:
        return {
            "status": self.mqtt_client_manager.get_connection_status(),
            "traffic": self.mqtt_client_manager.get_traffic_snapshot(),
        }

    def set_connection(self, enabled: bool) -> dict[str, bool]:
        if enabled:
            if self.mqtt_client_manager.get_connection_status() == "desconectado":
                threading.Thread(
                    target=self.mqtt_client_manager.start,
                    daemon=True,
                ).start()
        else:
            self.mqtt_client_manager.stop()
        return {"enabled": enabled}
