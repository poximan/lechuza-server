from __future__ import annotations

import threading
import time
from typing import Callable, Dict, Any

from .logger import logger


class Poller:
    def __init__(
        self,
        interval_seconds: int,
        collect_fn: Callable[[], Dict[str, Any]],
        on_snapshot: Callable[[Dict[str, Any]], None],
        publish_fn: Callable[[Dict[str, Any]], None],
        publish_every: int,
    ) -> None:
        self._interval = interval_seconds
        self._collect = collect_fn
        self._on_snapshot = on_snapshot
        self._publish = publish_fn
        self._publish_every = max(1, publish_every)
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run, name="pve-poller", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)

    def _run(self) -> None:
        publish_counter = self._publish_every
        while not self._stop_event.is_set():
            try:
                snapshot = self._collect()
                if isinstance(snapshot, tuple):
                    snapshot = snapshot[0]
            except Exception as exc:
                logger.log(f"Error en colecta PVE: {exc}", "PVE/POLL")
                snapshot = {
                    "ts": self._collect_failure_ts(),
                    "node": "desconocido",
                    "status": "offline",
                    "vms": [],
                    "missing": [],
                    "error": str(exc),
                }
            self._on_snapshot(snapshot)
            publish_counter -= 1
            if publish_counter <= 0:
                try:
                    self._publish(snapshot)
                except Exception as exc:
                    logger.log(f"Error publicando snapshot MQTT: {exc}", "PVE/MQTT")
                publish_counter = self._publish_every
            self._stop_event.wait(self._interval)

    @staticmethod
    def _collect_failure_ts() -> str:
        from .utils import timebox

        return timebox.utc_iso()
