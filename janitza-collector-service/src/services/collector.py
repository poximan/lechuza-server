from __future__ import annotations

import threading
from typing import Any

from modbus_transport_client import ModbusTcpReadOnlyDriver
from timeauthority import get_time_authority

from src.services.state_store import JanitzaStateStore


_TIME = get_time_authority()


def signed_word(value: int) -> int:
    return value - 65536 if value & 0x8000 else value


class JanitzaCollector:
    """Lee UMG96S por Modbus 03 y conserva sus relaciones inmutables."""

    ELECTRICAL_ADDRESS = 200
    ELECTRICAL_COUNT = 9
    TOTAL_POWER_ADDRESS = 279
    TOTAL_POWER_COUNT = 3
    TRANSFORMER_ADDRESS = 600
    TRANSFORMER_COUNT = 4

    def __init__(
        self,
        driver: ModbusTcpReadOnlyDriver,
        analyzers: list[dict[str, Any]],
        interval: int,
        store: JanitzaStateStore,
    ) -> None:
        self.driver = driver
        self.analyzers = analyzers
        self.interval = max(1, interval)
        self.store = store
        self.stop_event = threading.Event()
        self.thread = threading.Thread(
            target=self.run,
            name="janitza-monitor",
            daemon=True,
        )

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        self.thread.join(timeout=10)
        self.driver.shutdown()

    def run(self) -> None:
        while not self.stop_event.is_set():
            for analyzer in self.analyzers:
                if self.stop_event.is_set():
                    break
                try:
                    self.collect(analyzer)
                except Exception as exc:
                    print(
                        f"Fallo al actualizar Janitza {analyzer.get('id')}: "
                        f"{type(exc).__name__}: {exc}",
                        flush=True,
                    )
            self.stop_event.wait(self.interval)

    @staticmethod
    def _valid_ratios(value: Any) -> bool:
        if not isinstance(value, dict):
            return False
        required = (
            "current_primary_a",
            "current_secondary_a",
            "voltage_primary_v",
            "voltage_secondary_v",
        )
        return all(type(value.get(key)) is int and value[key] > 0 for key in required)

    def _load_ratios(
        self,
        unit_id: int,
        key: str,
        current: dict[str, Any],
        name: str,
    ) -> dict[str, Any] | None:
        persisted = current.get("transformer_ratios")
        if self._valid_ratios(persisted):
            return dict(persisted)

        words = self.driver.read_holding_registers(
            self.TRANSFORMER_ADDRESS,
            self.TRANSFORMER_COUNT,
            unit_id,
        )
        if words is None or len(words) != self.TRANSFORMER_COUNT:
            return None
        ratios = {
            "current_primary_a": int(words[0]),
            "current_secondary_a": int(words[1]),
            "voltage_primary_v": int(words[2]),
            "voltage_secondary_v": int(words[3]),
            "learned_at": _TIME.utc_iso(),
        }
        if not self._valid_ratios(ratios):
            return None

        self.store.update(
            key,
            {
                **current,
                "id": unit_id,
                "name": name,
                "transformer_ratios": ratios,
            },
        )
        return ratios

    def collect(self, analyzer: dict[str, Any]) -> None:
        unit_id = int(analyzer["id"])
        key = str(unit_id)
        name = str(analyzer["name"])
        attempted = _TIME.utc_iso()
        current = self.store.snapshot().get(key, {})
        ratios = self._load_ratios(unit_id, key, current, name)
        if ratios is None:
            self._store_failure(
                key,
                current,
                unit_id,
                name,
                attempted,
                "relaciones de transformacion no disponibles o invalidas",
            )
            return

        electrical = self.driver.read_holding_registers(
            self.ELECTRICAL_ADDRESS,
            self.ELECTRICAL_COUNT,
            unit_id,
        )
        powers = (
            self.driver.read_holding_registers(
                self.TOTAL_POWER_ADDRESS,
                self.TOTAL_POWER_COUNT,
                unit_id,
            )
            if electrical is not None
            else None
        )
        if (
            electrical is None
            or powers is None
            or len(electrical) != self.ELECTRICAL_COUNT
            or len(powers) != self.TOTAL_POWER_COUNT
        ):
            self._store_failure(
                key,
                current,
                unit_id,
                name,
                attempted,
                "lectura Modbus incompleta",
                ratios,
            )
            return

        current_factor = (
            ratios["current_primary_a"] / ratios["current_secondary_a"]
        )
        voltage_factor = (
            ratios["voltage_primary_v"] / ratios["voltage_secondary_v"]
        )
        power_factor = current_factor * voltage_factor
        measured_at = _TIME.utc_iso()
        payload = {
            "id": unit_id,
            "name": name,
            "status": "available",
            "measured_at": measured_at,
            "last_attempt_at": attempted,
            "error": None,
            "transformer_ratios": ratios,
            "voltage_ln_v": {
                "l1": electrical[0] / 10.0 * voltage_factor,
                "l2": electrical[1] / 10.0 * voltage_factor,
                "l3": electrical[2] / 10.0 * voltage_factor,
            },
            "voltage_ll_v": {
                "l1_l2": electrical[3] / 10.0 * voltage_factor,
                "l2_l3": electrical[4] / 10.0 * voltage_factor,
                "l3_l1": electrical[5] / 10.0 * voltage_factor,
            },
            "current_a": {
                "l1": electrical[6] / 1000.0 * current_factor,
                "l2": electrical[7] / 1000.0 * current_factor,
                "l3": electrical[8] / 1000.0 * current_factor,
            },
            "total_power": {
                "active_w": signed_word(powers[0]) * power_factor,
                "reactive_var": signed_word(powers[1]) * power_factor,
                "apparent_va": powers[2] * power_factor,
            },
            "raw": {
                "address_200": electrical,
                "address_279": powers,
                "address_600": [
                    ratios["current_primary_a"],
                    ratios["current_secondary_a"],
                    ratios["voltage_primary_v"],
                    ratios["voltage_secondary_v"],
                ],
            },
        }
        self.store.update(key, payload)

    def _store_failure(
        self,
        key: str,
        current: dict[str, Any],
        unit_id: int,
        name: str,
        attempted: str,
        error: str,
        ratios: dict[str, Any] | None = None,
    ) -> None:
        payload = {
            **current,
            "id": unit_id,
            "name": name,
            "status": "stale" if current.get("measured_at") else "unavailable",
            "last_attempt_at": attempted,
            "error": error,
        }
        if ratios is not None:
            payload["transformer_ratios"] = ratios
        self.store.update(key, payload)

    def snapshot(self) -> dict[str, Any]:
        values = self.store.snapshot()
        return {
            "items": [
                values.get(
                    str(item["id"]),
                    {
                        "id": item["id"],
                        "name": item["name"],
                        "status": "pending",
                        "measured_at": None,
                        "last_attempt_at": None,
                        "error": None,
                    },
                )
                for item in self.analyzers
            ],
            "poll_interval_seconds": self.interval,
        }
