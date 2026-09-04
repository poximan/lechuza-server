import threading
from typing import Any, Callable, Iterable

import requests

from config import Target
from timeauthority import get_time_authority
from state import StateStore
from broadcast import broadcast_state
from logger import logger

_AUTH = get_time_authority()


class CharitoPoller:
    def __init__(
            self,
            targets: Iterable[Target],
            state: StateStore,
            poll_interval: int,
            request_timeout: float,
            on_state: Callable[[dict], None],
    ) -> None:
        self._targets = list(targets)
        self._state = state
        self._interval = poll_interval
        self._timeout = request_timeout
        self._on_state = on_state
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._registry: dict[str, dict] = {}
        for target in self._targets:
            key = target.tracking_key
            self._registry[target.metrics_url] = {
                "target": target,
                "key": key,
                "alias": target.alias,
            }
            self._state.ensure_placeholder(key, target.alias)
        self._state.prune([target.instance_id for target in self._targets])
        self._log = logger

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run_loop, name="charito-poller", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)

    def _run_loop(self) -> None:
        while not self._stop.is_set():
            try:
                for target in self._targets:
                    if self._stop.is_set():
                        break
                    try:
                        self._poll_target(target)
                    except Exception:
                        self._log.exception("Error no controlado en ciclo de polling para %s", target.metrics_url, origin="CHARITO/POLLER")
                if not self._stop.is_set():
                    self._broadcast_state()
                self._stop.wait(self._interval)
            except Exception:
                self._log.exception("Fallo inesperado del loop de polling; se reintentara", origin="CHARITO/POLLER")
                self._stop.wait(min(self._interval, 5))

    def _poll_target(self, target: Target) -> None:
        registry = self._registry.get(target.metrics_url) or {}
        key_hint = registry.get("key") or target.tracking_key
        alias = registry.get("alias") or target.alias
        effective_id = target.instance_id
        try:
            response = requests.get(target.metrics_url, timeout=self._timeout)
        except requests.RequestException as exc:
            self._log.warning("Fallo consultando %s (%s): %s", target.alias, target.metrics_url, exc, origin="CHARITO/POLLER")
            try:
                self._state.mark_offline(effective_id, alias=alias)
            except Exception:
                self._log.exception("No se pudo persistir estado offline para %s", effective_id, origin="CHARITO/POLLER")
            return

        payload = None
        issue = None
        metrics: dict[str, Any] | None = None
        try:
            parsed = response.json()
            if isinstance(parsed, dict):
                metrics = parsed
            else:
                issue = "response_json_not_object"
        except Exception as exc:
            issue = f"invalid_json: {exc}"

        if issue is None and metrics is not None and response.status_code < 400:
            try:
                payload = self._build_payload(effective_id, metrics, alias)
            except Exception as exc:
                issue = f"invalid_metrics_payload: {exc}"

        if payload is None:
            reason = issue or f"http_status_{response.status_code}"
            if response.status_code >= 400 and metrics is not None:
                api_error = str(metrics.get("error") or "").strip()
                if api_error:
                    reason = f"http_status_{response.status_code}: {api_error}"
            self._log.warning(
                "Host reachable pero sin metricas utiles para %s (%s): %s",
                target.alias,
                target.metrics_url,
                reason,
                origin="CHARITO/POLLER",
            )
            payload = self._build_error_payload(
                instance_id=effective_id,
                alias=alias,
                http_status=response.status_code,
                reason=reason,
            )

        self._state.upsert_observation(payload, key_hint=key_hint, alias=alias)

    def _build_payload(self, instance_id: str, metrics: dict, alias: str) -> dict:
        network_info = metrics.get("networkInterfaces")
        if not isinstance(network_info, list):
            network_info = self._extract_interfaces(metrics)
        latest = metrics.get("latestSample")
        if not isinstance(latest, dict):
            latest = self._latest_sample(metrics, network_info)
        else:
            latest.setdefault("networkInterfaces", network_info)
        samples = int(metrics["samples"])
        window_seconds = int(metrics["windowSeconds"])
        timeout_seconds = int(metrics["timeoutSeconds"])
        cpu_load = float(metrics["cpuLoad"])
        temp_celsius = float(metrics["cpuTemperatureCelsius"])
        mem_ratio = float(metrics["memoryUsageRatio"])
        free_bytes = int(metrics["freeMemoryBytes"])
        total_bytes = int(metrics["totalMemoryBytes"])
        payload = {
            "instanceId": instance_id,
            "alias": alias,
            "status": "online",
            "hostReachable": True,
            "dataStatus": "ok",
            "generatedAt": metrics.get("generatedAt") or metrics.get("timestamp") or _AUTH.utc_iso(),
            "receivedAt": _AUTH.utc_iso(),
            "samples": samples,
            "windowSeconds": window_seconds,
            "timeoutSeconds": timeout_seconds,
            "cpuLoad": cpu_load,
            "cpuTemperatureCelsius": temp_celsius,
            "memoryUsageRatio": mem_ratio,
            "freeMemoryBytes": free_bytes,
            "totalMemoryBytes": total_bytes,
            "networkInterfaces": network_info,
            "watchedProcesses": latest.get("watchedProcesses", []),
            "latestSample": latest,
        }
        return payload

    def _latest_sample(self, metrics: dict, network_info: list | None = None) -> dict:
        sample = {
            "timestamp": metrics.get("latestSampleTimestamp") or metrics.get("generatedAt"),
            "cpuLoad": metrics.get("cpuLoad"),
            "cpuTemperatureCelsius": metrics.get("cpuTemperatureCelsius"),
            "totalMemoryBytes": metrics.get("totalMemoryBytes"),
            "freeMemoryBytes": metrics.get("freeMemoryBytes"),
            "watchedProcesses": metrics.get("watchedProcesses", []),
        }
        sample["networkInterfaces"] = network_info if network_info is not None else self._extract_interfaces(metrics)
        return sample

    def _broadcast_state(self) -> None:
        snapshot = self._state.build_state()
        self._on_state(snapshot)
        try:
            broadcast_state(snapshot)
        except Exception:
            self._log.exception("No se pudo publicar estado charito por MQTT", origin="CHARITO/MQTT")

    def _extract_interfaces(self, metrics: dict) -> list:
        interfaces = metrics.get("networkInterfaces") or []
        cleaned: list = []
        for entry in interfaces:
            if not isinstance(entry, dict):
                continue
            addresses = []
            for info in entry.get("addresses") or []:
                if not isinstance(info, dict):
                    continue
                address = str(info.get("address") or "").strip()
                netmask = str(info.get("netmask") or "").strip()
                addresses.append(
                    {
                        "address": address,
                        "netmask": netmask,
                    }
                )
            cleaned.append(
                {
                    "name": str(entry.get("name") or ""),
                    "displayName": str(entry.get("displayName") or ""),
                    "path": str(entry.get("path") or ""),
                    "macAddress": str(entry.get("macAddress") or ""),
                    "up": bool(entry.get("up")),
                    "virtual": bool(entry.get("virtual")),
                    "addresses": addresses,
                }
            )
        return cleaned

    def _build_error_payload(self, instance_id: str, alias: str, http_status: int, reason: str) -> dict:
        now_iso = _AUTH.utc_iso()
        latest = {
            "timestamp": now_iso,
            "cpuLoad": -1.0,
            "cpuTemperatureCelsius": -1.0,
            "totalMemoryBytes": 0,
            "freeMemoryBytes": 0,
            "watchedProcesses": [],
            "networkInterfaces": [],
        }
        return {
            "instanceId": instance_id,
            "alias": alias,
            "status": "error",
            "hostReachable": True,
            "generatedAt": now_iso,
            "receivedAt": now_iso,
            "samples": 0,
            "windowSeconds": 0,
            "timeoutSeconds": 0,
            "cpuLoad": -1.0,
            "cpuTemperatureCelsius": -1.0,
            "memoryUsageRatio": -1.0,
            "freeMemoryBytes": 0,
            "totalMemoryBytes": 0,
            "networkInterfaces": [],
            "watchedProcesses": [],
            "latestSample": latest,
            "httpStatus": int(http_status),
            "dataStatus": "metrics_unavailable",
            "dataError": reason,
        }
