import requests
import config


class RouterStatusClient:
    def __init__(self, base_url: str, timeout_seconds: float) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout_seconds

    def get_status(self) -> dict:
        url = f"{self.base_url}/status"
        resp = requests.get(url, timeout=self.timeout)
        resp.raise_for_status()
        data = resp.json()
        for key in ("ip", "port", "state"):
            if key not in data:
                raise ValueError(f"Respuesta invalida de router-service: falta {key}")
        data["ip"] = str(data["ip"])
        data["port"] = int(data["port"])
        data["state"] = str(data["state"])
        return data


modem_link_monitor_client = RouterStatusClient(
    base_url=config.MODEM_LINK_MONITOR_URL,
    timeout_seconds=float(config.MODEM_LINK_MONITOR_TIMEOUT_SECONDS),
)
