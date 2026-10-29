from typing import Any

import config
from src.web.clients.domain_http_client import DomainHttpClient


class JanitzaClient:
    def __init__(self) -> None:
        self.http = DomainHttpClient(
            config.JANITZA_COLLECTOR_API_BASE,
            config.MODBUS_COLLECTOR_HTTP_TIMEOUT,
        )

    def get_analyzers(self) -> dict[str, Any]:
        return self.http.request("GET", "/api/analizadores")

    def set_observer(self, enabled: bool) -> bool:
        payload = self.http.request(
            "POST", "/api/analizadores/observer", body={"enabled": enabled}
        )
        if type(payload.get("enabled")) is not bool:
            raise RuntimeError("Contrato Janitza invalido: enabled debe ser booleano")
        return payload["enabled"]


janitza_client = JanitzaClient()
