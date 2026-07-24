import time
from typing import Any, Dict, Optional

import certifi
import requests

from .logger import logger


class TcpProbe:
    def __init__(
        self,
        base_url: str,
        max_nodes: int,
        success_latency: float,
        result_timeout: float,
        poll_interval: float,
        request_timeout: float,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.max_nodes = max_nodes
        self.success_latency = success_latency
        self.result_timeout = result_timeout
        self.poll_interval = poll_interval
        self.request_timeout = request_timeout
        self.session = requests.Session()
        self.session.verify = certifi.where()
        self.headers = {"Accept": "application/json"}

    def check(self, host: str, port: int) -> str:
        try:
            request_id = self._start_check(host, port)
        except Exception as exc:
            logger.error("No se pudo iniciar el chequeo TCP: %s", exc, origin="ROUTER-TELEF/TCP")
            return "desconocido"

        deadline = time.monotonic() + self.result_timeout
        failure_detected = False

        while time.monotonic() < deadline:
            try:
                nodes = self._fetch_results(request_id)
            except Exception as exc:
                logger.warning("Error obteniendo resultados para %s: %s", request_id, exc, origin="ROUTER-TELEF/TCP")
                time.sleep(self.poll_interval)
                continue

            if not nodes:
                time.sleep(self.poll_interval)
                continue

            pending = False
            for node_name, results in nodes.items():
                if results is None:
                    pending = True
                    continue
                if not isinstance(results, list) or not results:
                    continue

                first = results[0]
                if not isinstance(first, dict):
                    continue

                latency = self._extract_latency(first)
                if latency is not None:
                    logger.info("Nodo %s reporto tiempo %.2f s", node_name, latency, origin="ROUTER-TELEF/TCP")
                    if latency <= self.success_latency:
                        return "abierto"
                    failure_detected = True
                    continue

                error_msg = first.get("error")
                if error_msg:
                    logger.warning("Nodo %s reporto error: %s", node_name, error_msg, origin="ROUTER-TELEF/TCP")
                    failure_detected = True
                    continue

                pending = True

            if failure_detected and not pending:
                return "cerrado"

            time.sleep(self.poll_interval)

        if failure_detected:
            return "cerrado"
        return "desconocido"

    def _start_check(self, host: str, port: int) -> str:
        params = {
            "host": f"{host}:{port}",
            "max_nodes": self.max_nodes,
        }
        response = self.session.get(
            f"{self.base_url}/check-tcp",
            params=params,
            headers=self.headers,
            timeout=self.request_timeout,
        )
        response.raise_for_status()
        data = response.json()
        request_id = data.get("request_id")
        if not data.get("ok") or not request_id:
            raise ValueError(f"Respuesta invalida al iniciar chequeo: {data}")
        return str(request_id)

    def _fetch_results(self, request_id: str) -> Dict[str, Any]:
        response = self.session.get(
            f"{self.base_url}/check-result/{request_id}",
            headers=self.headers,
            timeout=self.request_timeout,
        )
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise ValueError("Respuesta de resultados invalida")
        return data

    @staticmethod
    def _extract_latency(entry: Dict[str, Any]) -> Optional[float]:
        value = entry.get("time")
        if isinstance(value, (int, float)):
            return float(value)
        return None