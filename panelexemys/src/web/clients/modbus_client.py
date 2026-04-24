import threading
import time
from typing import Any, Dict

import requests

import config


class ModbusMiddlewareHttpClient:
    """
    Cliente HTTP del servicio modbus-mw-service.
    Mantiene una sesion propia y expone helpers de alto nivel.
    """

    def __init__(self) -> None:
        self.base_url = config.MODBUS_MW_API_BASE.rstrip("/")
        self.timeout = int(config.MODBUS_MW_HTTP_TIMEOUT)
        self._session = requests.Session()
        self._lock = threading.RLock()
        self._descriptions_cache: Dict[int, str] | None = None
        self._descriptions_ts = 0.0
        self._descriptions_ttl = 300.0  # 5 minutos

    def _request(
        self,
        method: str,
        path: str,
        json_body: Dict[str, Any] | None = None,
        params: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        url = f"{self.base_url}{path}"
        resp = self._session.request(method, url, timeout=self.timeout, json=json_body, params=params)
        resp.raise_for_status()
        data = resp.json()
        if not isinstance(data, dict):
            raise RuntimeError(f"Respuesta inesperada desde {url}")
        return data

    def get_descriptions(self) -> Dict[int, str]:
        with self._lock:
            now = time.time()
            if self._descriptions_cache is not None and (now - self._descriptions_ts) < self._descriptions_ttl:
                return self._descriptions_cache
            data = self._request("GET", "/api/grd/descriptions")
            items = data.get("items") or {}
            mapped = {int(k): str(v) for k, v in items.items()}
            self._descriptions_cache = mapped
            self._descriptions_ts = now
            return mapped

    def get_summary(self) -> Dict[str, Any]:
        return self._request("GET", "/api/grd/summary")

    def get_history(self, grd_id: int, window: str, page: int) -> Dict[str, Any]:
        params = {"grd_id": grd_id, "window": window, "page": page}
        return self._request("GET", "/api/grd/history", params=params)

    def get_outages(self, grd_id: int, limit: int = 10) -> Dict[str, Any]:
        params = {"grd_id": grd_id, "limit": limit}
        return self._request("GET", "/api/grd/outages", params=params)

    def get_reles_faults(self) -> Dict[str, Any]:
        return self._request("GET", "/api/reles/faults")

    def get_reles_observer(self) -> bool:
        data = self._request("GET", "/api/reles/observer")
        return bool(data.get("enabled", False))

    def set_reles_observer(self, enabled: bool) -> bool:
        data = self._request("POST", "/api/reles/observer", {"enabled": bool(enabled)})
        return bool(data.get("enabled", False))

    def get_ge_status(self) -> Dict[str, Any]:
        return self._request("GET", "/api/ge/status")


modbus_client = ModbusMiddlewareHttpClient()
