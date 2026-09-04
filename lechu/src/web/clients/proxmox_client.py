from typing import Any, Dict
import requests

class ProxmoxClient:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = 2.0

    def _get(self, path: str, timeout: float | None = None) -> Dict[str, Any]:
        url = f"{self.base_url}{path}"
        try:
            resp = requests.get(url, timeout=timeout or self.timeout)
            if resp.status_code >= 400:
                raise requests.HTTPError(f"{resp.status_code}: {resp.text}")
            return resp.json()
        except Exception as exc:
            raise RuntimeError(f"ProxmoxClient GET failed: {exc}") from exc

    def get_state(self) -> Dict[str, Any]:
        return self._get("/api/pve/state")

    def get_history(self) -> Dict[str, Any]:
        return self._get("/api/pve/history", timeout=10.0)
