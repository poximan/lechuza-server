import math
import time
from typing import Any

import certifi
import requests
from timeauthority import get_time_authority


_TIME = get_time_authority()


class GlobalpingTcpProbe:
    """TCP connect measurements; ICMP replies never establish port availability."""

    def __init__(self, base_url: str, result_timeout: float, poll_interval: float,
                 request_timeout: float, failure_confirmation: float, max_nodes: int = 3):
        self.base_url = base_url.rstrip("/")
        self.result_timeout = result_timeout
        self.poll_interval = poll_interval
        self.request_timeout = request_timeout
        self.failure_confirmation = failure_confirmation
        self.max_nodes = max_nodes
        self.session = requests.Session()
        self.session.verify = certifi.where()

    def check(self, host: str, port: int) -> dict[str, Any]:
        started = _TIME.monotonic()
        nodes: list[dict[str, Any]] = []
        request_id = None
        state = "desconocido"
        error = None
        try:
            response = self.session.post(f"{self.base_url}/v1/measurements", json={
                "type": "ping", "target": host, "limit": self.max_nodes,
                "locations": [{"continent": "SA"}, {"continent": "NA"}, {"continent": "EU"}],
                "measurementOptions": {"protocol": "TCP", "port": port, "packets": 1},
                "inProgressUpdates": True,
            }, timeout=self.request_timeout)
            response.raise_for_status()
            data = response.json()
            request_id = data.get("id") if isinstance(data, dict) else None
            if not isinstance(request_id, str) or not request_id.isalnum():
                raise ValueError("Globalping no informo un identificador de medicion valido")
            deadline = _TIME.monotonic() + self.result_timeout
            failure_since = None
            while _TIME.monotonic() < deadline:
                try:
                    response = self.session.get(f"{self.base_url}/v1/measurements/{request_id}",
                        timeout=min(self.request_timeout, max(.001, deadline - _TIME.monotonic())))
                    response.raise_for_status()
                    data = response.json()
                    if (not isinstance(data, dict) or data.get("type") != "ping"
                            or data.get("target") != host
                            or data.get("measurementOptions", {}).get("protocol") != "TCP"
                            or data.get("measurementOptions", {}).get("port") != port
                            or not isinstance(data.get("results"), list)):
                        raise ValueError("Respuesta de medicion TCP Globalping incompatible")
                    nodes = self._describe_nodes(data["results"])
                    error = None
                except requests.RequestException as exc:
                    if isinstance(exc, requests.HTTPError) and exc.response is not None and exc.response.status_code == 429:
                        raise
                    error = str(exc)
                    time.sleep(min(self.poll_interval, max(0, deadline - _TIME.monotonic())))
                    continue
                if any(node["status"] == "conectado" for node in nodes):
                    state = "abierto"
                    for node in nodes:
                        if node["status"] == "pendiente":
                            node["status"] = "no_esperado"
                    break
                all_failed = len(nodes) == self.max_nodes and all(
                    node["status"] == "desconectado" for node in nodes)
                if all_failed:
                    if failure_since is None:
                        failure_since = _TIME.monotonic()
                    if _TIME.monotonic() - failure_since >= self.failure_confirmation:
                        state = "cerrado"
                        break
                else:
                    failure_since = None
                    if data.get("status") == "finished":
                        break
                time.sleep(min(self.poll_interval, max(0, deadline - _TIME.monotonic())))
        except Exception as exc:
            error = str(exc)
        if state == "desconocido":
            for node in nodes:
                if node["status"] == "pendiente":
                    node["status"] = "sin_resultado"
            error = error or "Globalping no completo un chequeo TCP concluyente"
        attempt = {"provider": "Globalping", "number": 1, "state": state, "nodes": nodes,
                   "request_id": request_id, "error": error}
        return {**attempt, "attempts": [attempt],
                "elapsed_seconds": round(_TIME.monotonic() - started, 3)}

    @staticmethod
    def _describe_nodes(results: list) -> list[dict[str, Any]]:
        nodes = []
        for index, entry in enumerate(results):
            if not isinstance(entry, dict) or not isinstance(entry.get("probe"), dict):
                raise ValueError("Resultado de sonda Globalping invalido")
            probe = entry["probe"]
            result = entry.get("result") or {}
            if not isinstance(result, dict):
                raise ValueError("Resultado TCP Globalping invalido")
            stats = result.get("stats") or {}
            if not isinstance(stats, dict):
                raise ValueError("Estadisticas TCP Globalping invalidas")
            total, received = stats.get("total"), stats.get("rcv")
            valid = (type(total) is int and type(received) is int
                     and total > 0 and 0 <= received <= total)
            node = {"id": f'{probe.get("country", "?")}/{probe.get("city", "?")}/AS{probe.get("asn", "?")}/{index + 1}',
                    "country": probe.get("country"), "city": probe.get("city"),
                    "probe_ip": None, "status": "pendiente", "error": None,
                    "latency_seconds": None}
            if valid and received > 0:
                node["status"] = "conectado"
                latency = stats.get("avg")
                if type(latency) in {int, float} and math.isfinite(latency) and latency >= 0:
                    node["latency_seconds"] = latency / 1000
            elif valid and result.get("status") == "finished":
                node["status"] = "desconectado"
                node["error"] = "La sonda no pudo establecer la conexion TCP"
            elif result.get("status") in {"failed", "offline", "finished"}:
                node["status"] = "error_nodo"
                node["error"] = "La sonda no entrego una medicion TCP valida"
            nodes.append(node)
        return nodes


class ExternalTcpProbe:
    def __init__(self, globalping: GlobalpingTcpProbe, check_host: Any, primary: str = "globalping"):
        self.globalping = globalping
        self.check_host = check_host
        self.primary = primary

    def check(self, host: str, port: int) -> dict[str, Any]:
        if self.primary == "check-host":
            return self.check_host.check(host, port)
        started = _TIME.monotonic()
        primary = self.globalping.check(host, port)
        if primary["state"] != "desconocido":
            return primary
        fallback = self.check_host.check(host, port)
        attempts = []
        for source in (primary, fallback):
            for attempt in source.get("attempts", []):
                attempts.append({**attempt, "number": len(attempts) + 1})
        return {**fallback, "attempts": attempts,
                "elapsed_seconds": round(_TIME.monotonic() - started, 3)}
