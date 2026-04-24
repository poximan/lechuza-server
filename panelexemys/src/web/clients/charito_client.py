import requests
from typing import Any, Dict, List, Optional


class CharitoClient:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = 2.0
        self.retries = 2

    def _get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        url = f"{self.base_url}{path}"
        last_exc = None
        for _ in range(self.retries + 1):
            try:
                resp = requests.get(url, params=params, timeout=self.timeout)
                if resp.status_code >= 400:
                    raise requests.HTTPError(f"{resp.status_code}: {resp.text}")
                return resp.json()
            except Exception as exc:
                last_exc = exc
        raise RuntimeError(f"CharitoClient GET failed: {last_exc}")

    def get_state(self, instance_ids: Optional[List[str]] = None) -> Dict[str, Any]:
        params = None
        if instance_ids:
            params = {"ids": ",".join(instance_ids)}
        return self._get("/api/charito/state", params=params)

    def list_instances(self, since: Optional[str] = None) -> Dict[str, Any]:
        params = {"since": since} if since else None
        return self._get("/api/charito/instances", params=params)
