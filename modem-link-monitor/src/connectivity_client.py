import math

import requests


class GrdConnectivityClient:
    def __init__(self, base_url: str, timeout_seconds: float) -> None:
        self._url = f"{base_url.rstrip('/')}/api/grd/summary"
        self._timeout_seconds = timeout_seconds

    def percentage(self) -> float:
        response = requests.get(self._url, timeout=self._timeout_seconds)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or not isinstance(payload.get("summary"), dict):
            raise ValueError("Resumen GRD sin objeto summary")
        value = payload["summary"].get("porcentaje")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("Resumen GRD sin porcentaje numerico")
        percentage = float(value)
        if not math.isfinite(percentage) or not 0 <= percentage <= 100:
            raise ValueError("Porcentaje de conectividad GRD fuera de rango")
        return percentage
