import json
from dataclasses import dataclass
from typing import List


@dataclass(frozen=True)
class Target:
    alias: str
    instance_id: str
    metrics_url: str

    @property
    def tracking_key(self) -> str:
        return self.instance_id

    @staticmethod
    def from_dict(entry: dict) -> "Target":
        instance_id = _required_text(entry, "id")
        alias = _required_text(entry, "alias")
        base_url = _required_text(entry, "baseUrl").rstrip("/")
        metrics_path = "/metrics"
        base_url = base_url.rstrip("/")
        metrics_url = f"{base_url}{metrics_path}"
        return Target(alias=alias, instance_id=instance_id, metrics_url=metrics_url)


@dataclass(frozen=True)
class ServiceConfig:
    poll_interval_seconds: int
    http_timeout_seconds: float
    instances: List[Target]


def _required_text(entry: dict, key: str) -> str:
    value = entry.get(key)
    if value is None or not str(value).strip():
        raise ValueError(f"Cada instancia debe definir '{key}'")
    return str(value).strip()


def _build_service_config(items: list, poll_interval: int, http_timeout: float) -> ServiceConfig:
    if not isinstance(items, list) or not items:
        raise ValueError("El archivo de targets debe contener una lista 'instances'")
    targets = []
    for entry in items:
        if not isinstance(entry, dict):
            raise ValueError("Cada elemento de 'instances' debe ser un objeto JSON")
        targets.append(Target.from_dict(entry))
    if not targets:
        raise ValueError("La lista de instancias esta vacia")
    return ServiceConfig(
        poll_interval_seconds=poll_interval,
        http_timeout_seconds=http_timeout,
        instances=targets,
    )


def load_service_config_from_json(raw: str) -> ServiceConfig:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"CHARITO_TARGETS_JSON no contiene JSON valido: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("CHARITO_TARGETS_JSON debe contener un objeto JSON")
    if "pollIntervalSeconds" not in data:
        raise ValueError("CHARITO_TARGETS_JSON debe definir 'pollIntervalSeconds'")
    if "httpTimeoutSeconds" not in data:
        raise ValueError("CHARITO_TARGETS_JSON debe definir 'httpTimeoutSeconds'")
    poll_interval = int(data["pollIntervalSeconds"])
    http_timeout = float(data["httpTimeoutSeconds"])
    if poll_interval <= 0:
        raise ValueError("'pollIntervalSeconds' debe ser mayor que cero")
    if http_timeout <= 0:
        raise ValueError("'httpTimeoutSeconds' debe ser mayor que cero")
    items = data.get("instances")
    return _build_service_config(items, poll_interval=poll_interval, http_timeout=http_timeout)
