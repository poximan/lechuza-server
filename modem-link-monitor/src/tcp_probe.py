import math
import time
from timeauthority import get_time_authority
from typing import Any

import certifi
import requests

from .logger import logger


time_provider = get_time_authority()


class TcpProbe:
    def __init__(
        self,
        base_url: str,
        max_nodes: int,
        failure_confirmation: float,
        result_timeout: float,
        poll_interval: float,
        request_timeout: float,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.max_nodes = max_nodes
        self.failure_confirmation = failure_confirmation
        self.result_timeout = result_timeout
        self.poll_interval = poll_interval
        self.request_timeout = request_timeout
        self.session = requests.Session()
        self.session.verify = certifi.where()
        self.headers = {"Accept": "application/json"}

    def check(self, host: str, port: int) -> dict[str, Any]:
        try:
            request_id, selected = self._start_check(host, port)
        except Exception as exc:
            logger.error("No se pudo iniciar el chequeo TCP: %s", exc, origin="ROUTER-TELEF/TCP")
            return {"state": "desconocido", "nodes": [], "error": str(exc)}

        started_at = time_provider.monotonic()
        deadline = started_at + self.result_timeout
        nodes = self._describe_nodes(selected, {})
        while time_provider.monotonic() < deadline:
            try:
                results = self._fetch_results(request_id)
                latest = self._describe_nodes(selected, results)
                previous = {node["id"]: node for node in nodes}
                for node in latest:
                    earlier = previous[node["id"]]
                    if earlier["status"] == "conectado" or (
                        earlier["status"] == "desconectado" and node["status"] == "pendiente"
                    ):
                        node.update(earlier)
                nodes = latest
            except Exception as exc:
                logger.warning(
                    "Error obteniendo resultados para %s: %s",
                    request_id,
                    exc,
                    origin="ROUTER-TELEF/TCP",
                )
                self._wait_until_next_poll(deadline)
                continue

            connected = any(node["status"] == "conectado" for node in nodes)
            completed = all(node["status"] != "pendiente" for node in nodes)
            if completed and connected:
                return {"state": "abierto", "nodes": nodes, "request_id": request_id}
            if (
                len(nodes) == self.max_nodes
                and completed
                and not connected
                and time_provider.monotonic() - started_at >= self.failure_confirmation
            ):
                return {"state": "cerrado", "nodes": nodes, "request_id": request_id}
            if completed and len(nodes) < self.max_nodes:
                return {"state": "desconocido", "nodes": nodes, "request_id": request_id}
            self._wait_until_next_poll(deadline)

        state = "abierto" if any(node["status"] == "conectado" for node in nodes) else "desconocido"
        return {"state": state, "nodes": nodes, "request_id": request_id}

    def _wait_until_next_poll(self, deadline: float) -> None:
        remaining = deadline - time_provider.monotonic()
        if remaining > 0:
            time.sleep(min(self.poll_interval, remaining))

    def _start_check(self, host: str, port: int) -> tuple[str, dict[str, Any]]:
        response = self.session.get(
            f"{self.base_url}/check-tcp",
            params={"host": f"{host}:{port}", "max_nodes": self.max_nodes},
            headers=self.headers,
            timeout=self.request_timeout,
        )
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict) or not data.get("ok") or not data.get("request_id"):
            raise ValueError(f"Respuesta invalida al iniciar chequeo: {data}")
        selected = data.get("nodes")
        if not isinstance(selected, dict) or not selected or len(selected) > self.max_nodes:
            raise ValueError("Check-Host no informo un conjunto valido de nodos")
        if any(not isinstance(name, str) or not name for name in selected):
            raise ValueError("Check-Host informo un identificador de nodo invalido")
        return str(data["request_id"]), selected

    def _fetch_results(self, request_id: str) -> dict[str, Any]:
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

    @classmethod
    def _describe_nodes(
        cls, selected: dict[str, Any], results: dict[str, Any]
    ) -> list[dict[str, Any]]:
        described = []
        for name, location in selected.items():
            metadata = location if isinstance(location, list) else []
            result = results.get(name)
            first = result[0] if isinstance(result, list) and result else None
            node: dict[str, Any] = {
                "id": name,
                "country": str(metadata[1]) if len(metadata) > 1 else None,
                "city": str(metadata[2]) if len(metadata) > 2 else None,
                "probe_ip": str(metadata[3]) if len(metadata) > 3 else None,
                "status": "pendiente",
                "latency_seconds": None,
                "error": None,
            }
            if isinstance(first, dict):
                error = first.get("error")
                latency = cls._extract_latency(first)
                if error:
                    node["status"] = "desconectado"
                    node["error"] = str(error)
                elif latency is not None:
                    node["status"] = "conectado"
                    node["latency_seconds"] = latency
            described.append(node)
        return described

    @staticmethod
    def _extract_latency(entry: dict[str, Any]) -> float | None:
        value = entry.get("time")
        if (
            not isinstance(value, bool)
            and isinstance(value, (int, float))
            and math.isfinite(value)
            and value >= 0
        ):
            return float(value)
        return None
