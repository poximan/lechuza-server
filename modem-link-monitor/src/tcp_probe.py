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
        max_attempts: int = 2,
        node_cooldown: float = 900,
        nodes_refresh: float = 3600,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.max_nodes = max_nodes
        self.failure_confirmation = failure_confirmation
        self.result_timeout = result_timeout
        self.poll_interval = poll_interval
        self.request_timeout = request_timeout
        self.max_attempts = max_attempts
        self.node_cooldown = node_cooldown
        self.nodes_refresh = nodes_refresh
        self._catalog: dict[str, Any] = {}
        self._catalog_expires = 0.0
        self._last_used: dict[str, float] = {}
        self._cooldown_until: dict[str, float] = {}
        self.session = requests.Session()
        self.session.verify = certifi.where()
        self.headers = {"Accept": "application/json"}

    def check(self, host: str, port: int) -> dict[str, Any]:
        started_at = time_provider.monotonic()
        attempts = []
        excluded: set[str] = set()
        self._refresh_nodes()
        for number in range(1, self.max_attempts + 1):
            candidates = self._choose_nodes(excluded)
            # Do not ask the provider to choose again if it could reuse a failed batch.
            if number > 1 and not candidates:
                break
            if self._catalog and not candidates:
                break
            try:
                request_id, selected = self._start_check(host, port, candidates)
                used_at = time_provider.monotonic()
                for name in selected:
                    self._last_used[name] = used_at
                excluded.update(selected)
                attempt = self._poll_check(request_id, selected)
            except Exception as exc:
                logger.warning("No se pudo completar el chequeo TCP: %s", exc, origin="ROUTER-TELEF/TCP")
                excluded.update(candidates)
                attempt = {"state": "desconocido", "nodes": [], "error": str(exc)}
                # A rate limit applies to the API, not to one particular node.
                if isinstance(exc, requests.HTTPError) and exc.response is not None and exc.response.status_code == 429:
                    attempt["number"] = number
                    attempt["provider"] = "Check-Host"
                    attempts.append(attempt)
                    break
            attempt["number"] = number
            attempt["provider"] = "Check-Host"
            attempts.append(attempt)
            now = time_provider.monotonic()
            for node in attempt["nodes"]:
                if node["status"] in {"sin_resultado", "error_nodo"}:
                    self._cooldown_until[node["id"]] = now + self.node_cooldown
                elif node["status"] == "conectado":
                    self._cooldown_until.pop(node["id"], None)
            if attempt["state"] != "desconocido":
                break
        latest = attempts[-1] if attempts else {
            "state": "desconocido", "nodes": [],
            "error": "No hay sondas disponibles fuera del periodo de descanso",
        }
        result = {**latest, "provider": "Check-Host", "attempts": attempts,
                  "elapsed_seconds": round(time_provider.monotonic() - started_at, 3)}
        result.pop("number", None)
        return result

    def _refresh_nodes(self) -> None:
        now = time_provider.monotonic()
        if now < self._catalog_expires:
            return
        try:
            response = self.session.get(
                f"{self.base_url}/nodes/hosts", headers=self.headers, timeout=self.request_timeout,
            )
            response.raise_for_status()
            payload = response.json()
            catalog = payload.get("nodes") if isinstance(payload, dict) else None
            if not isinstance(catalog, dict) or not catalog:
                raise ValueError("Catalogo de sondas invalido")
            parsed_catalog = {
                name: data for name, data in catalog.items()
                if isinstance(name, str) and name and isinstance(data, dict)
                and isinstance(data.get("location"), list)
            }
            if not parsed_catalog:
                raise ValueError("Catalogo sin sondas utilizables")
            self._catalog = parsed_catalog
            self._catalog_expires = now + self.nodes_refresh
        except Exception as exc:
            self._catalog_expires = now + min(60, self.nodes_refresh)
            logger.warning("No se pudo actualizar el catalogo de sondas: %s", exc, origin="ROUTER-TELEF/TCP")

    def _choose_nodes(self, excluded: set[str]) -> list[str]:
        now = time_provider.monotonic()
        available = [name for name in self._catalog
                     if name not in excluded and self._cooldown_until.get(name, 0) <= now]
        chosen: list[str] = []
        countries: set[str] = set()
        networks: set[str] = set()
        while available and len(chosen) < self.max_nodes:
            def rank(name: str) -> tuple:
                metadata = self._catalog[name]
                location = metadata["location"]
                country = str(location[0]) if location else ""
                return (self._last_used.get(name, -1),
                        country in countries, str(metadata.get("asn", "")) in networks, name)
            name = min(available, key=rank)
            available.remove(name)
            chosen.append(name)
            metadata = self._catalog[name]
            countries.add(str(metadata["location"][0]) if metadata["location"] else "")
            networks.add(str(metadata.get("asn", "")))
        return chosen

    def _poll_check(self, request_id: str, selected: dict[str, Any]) -> dict[str, Any]:
        started_at = time_provider.monotonic()
        deadline = started_at + self.result_timeout
        nodes = self._describe_nodes(selected, {})
        failure_since = None
        last_error = None
        while time_provider.monotonic() < deadline:
            try:
                results = self._fetch_results(request_id, deadline)
                last_error = None
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
                if isinstance(exc, requests.HTTPError) and exc.response is not None and exc.response.status_code == 429:
                    raise
                last_error = str(exc)
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
            if connected:
                for node in nodes:
                    if node["status"] == "pendiente":
                        node["status"] = "no_esperado"
                return {"state": "abierto", "nodes": nodes, "request_id": request_id}
            all_failed = len(nodes) == self.max_nodes and all(
                node["status"] == "desconectado" for node in nodes)
            if all_failed:
                if failure_since is None:
                    failure_since = time_provider.monotonic()
                if time_provider.monotonic() - failure_since >= self.failure_confirmation:
                    return {"state": "cerrado", "nodes": nodes, "request_id": request_id}
            else:
                failure_since = None
                if completed:
                    break
            self._wait_until_next_poll(deadline)

        for node in nodes:
            if node["status"] == "pendiente":
                node["status"] = "sin_resultado"
                node["error"] = "La sonda no entrego un resultado dentro del plazo"
        return {"state": "desconocido", "nodes": nodes, "request_id": request_id,
                "error": last_error or "El proveedor no completo un chequeo concluyente"}

    def _wait_until_next_poll(self, deadline: float) -> None:
        remaining = deadline - time_provider.monotonic()
        if remaining > 0:
            time.sleep(min(self.poll_interval, remaining))

    def _start_check(self, host: str, port: int, nodes: list[str]) -> tuple[str, dict[str, Any]]:
        params: dict[str, Any] = {"host": f"{host}:{port}", "max_nodes": self.max_nodes}
        if nodes:
            params["node"] = nodes
        response = self.session.get(
            f"{self.base_url}/check-tcp",
            params=params,
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
        if nodes and not set(selected).issubset(nodes):
            raise ValueError("Check-Host no respeto la seleccion de sondas")
        return str(data["request_id"]), selected

    def _fetch_results(self, request_id: str, deadline: float) -> dict[str, Any]:
        response = self.session.get(
            f"{self.base_url}/check-result/{request_id}",
            headers=self.headers,
            timeout=min(self.request_timeout, max(0.001, deadline - time_provider.monotonic())),
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
                    # Unknown/internal node errors cannot establish a target outage.
                    target_errors = {"connection timed out", "connection refused", "no route to host",
                                     "host is down", "network is unreachable"}
                    node["status"] = ("desconectado" if str(error).strip().lower() in target_errors
                                      else "error_nodo")
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
