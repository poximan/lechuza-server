from __future__ import annotations

import json
import os
from dataclasses import dataclass


def required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Falta variable obligatoria: {name}")
    return value


def positive_integer(name: str) -> int:
    value = int(required(name))
    if value < 1:
        raise RuntimeError(f"{name} debe ser mayor que cero")
    return value


@dataclass(frozen=True)
class EndpointConfig:
    name: str
    host: str
    port: int
    timeout_seconds: int
    attempts: int


API_KEY = required("MODBUS_TRANSPORT_API_KEY")
QUEUE_MAXSIZE = positive_integer("MODBUS_TRANSPORT_QUEUE_MAXSIZE")
WAIT_TIMEOUT_SECONDS = positive_integer("MODBUS_TRANSPORT_WAIT_TIMEOUT_SECONDS")


def load_endpoint_configs() -> list[EndpointConfig]:
    raw = json.loads(required("MODBUS_TRANSPORT_ENDPOINTS_JSON"))
    if not isinstance(raw, list) or not raw:
        raise RuntimeError("MODBUS_TRANSPORT_ENDPOINTS_JSON debe ser una lista no vacia")
    endpoints: list[EndpointConfig] = []
    names: set[str] = set()
    targets: set[tuple[str, int]] = set()
    for item in raw:
        if not isinstance(item, dict):
            raise RuntimeError("Cada endpoint Modbus debe ser un objeto")
        endpoint = EndpointConfig(
            name=str(item.get("name", "")).strip(),
            host=str(item.get("host", "")).strip(),
            port=int(item.get("port", 0)),
            timeout_seconds=int(item.get("timeout_seconds", 0)),
            attempts=int(item.get("attempts", 0)),
        )
        if not endpoint.name or not endpoint.host:
            raise RuntimeError("Cada endpoint Modbus requiere name y host")
        if not 1 <= endpoint.port <= 65535:
            raise RuntimeError(f"Puerto invalido para {endpoint.name}")
        if endpoint.timeout_seconds < 1 or endpoint.attempts < 1:
            raise RuntimeError(f"Timeout e intentos invalidos para {endpoint.name}")
        target = (endpoint.host, endpoint.port)
        if endpoint.name in names:
            raise RuntimeError("Los nombres de endpoints Modbus deben ser unicos")
        if target in targets:
            raise RuntimeError(
                f"El endpoint fisico {endpoint.host}:{endpoint.port} esta duplicado"
            )
        names.add(endpoint.name)
        targets.add(target)
        endpoints.append(endpoint)
    return endpoints
