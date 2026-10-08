import copy
import threading
from typing import Any

from src.utils import timebox


class RouteTraceService:
    def __init__(self, client: Any, refresh_seconds: float = 300) -> None:
        self.client = client
        self.refresh_seconds = refresh_seconds
        self._lock = threading.Lock()
        self._target: tuple[str, int] | None = None
        self._snapshot: dict[str, Any] = self._empty_snapshot()
        self._next_run = 0.0
        self._running = False

    @staticmethod
    def _empty_snapshot() -> dict[str, Any]:
        return {
            "status": "sin_datos",
            "protocol": "UDP",
            "updated_at": None,
            "hops": [],
            "probed_hops": 0,
            "reached": False,
            "tcp": {"status": "sin_datos", "latency_ms": None, "error": None},
            "error": None,
        }

    def snapshot(self, ip: str | None, port: int | None) -> dict[str, Any]:
        if ip is None or port is None:
            return self._empty_snapshot()
        target = (ip, port)
        with self._lock:
            if target != self._target:
                self._target = target
                self._snapshot = self._empty_snapshot()
                self._next_run = 0.0
                self._running = False
            if not self._running and timebox.monotonic() >= self._next_run:
                self._running = True
                self._next_run = timebox.monotonic() + self.refresh_seconds
                threading.Thread(target=self._refresh, args=(target,), daemon=True).start()
            snapshot = copy.deepcopy(self._snapshot)
            snapshot["running"] = self._running
            return snapshot

    def _refresh(self, target: tuple[str, int]) -> None:
        try:
            result = self.client.trace(*target)
            snapshot = {
                "status": "ok",
                "protocol": "UDP",
                "updated_at": timebox.utc_iso(),
                **result,
            }
        except Exception as exc:
            snapshot = {
                "status": "error",
                "protocol": "UDP",
                "updated_at": timebox.utc_iso(),
                "hops": [],
                "probed_hops": 0,
                "reached": False,
                "tcp": {"status": "sin_datos", "latency_ms": None, "error": None},
                "error": f"{type(exc).__name__}: {exc}",
            }
        with self._lock:
            if target == self._target:
                self._snapshot = snapshot
                self._running = False
