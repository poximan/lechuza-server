from __future__ import annotations

import threading
from typing import Callable, Dict, Any

from .logger import logger


class Poller:
    def __init__(
        self,
        interval_seconds: int,
        collect_fn: Callable[[], Dict[str, Any]],
        on_snapshot: Callable[[Dict[str, Any]], None],
        on_failure: Callable[[Dict[str, Any]], None],
        publish_fn: Callable[[Dict[str, Any]], None],
        publish_every: int,
        initial_snapshot: Dict[str, Any] | None = None,
    ) -> None:
        self._interval = interval_seconds
        self._collect = collect_fn
        self._on_snapshot = on_snapshot
        self._on_failure = on_failure
        self._publish = publish_fn
        self._publish_every = max(1, publish_every)
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_successful_snapshot = dict(initial_snapshot) if initial_snapshot else None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run, name="pve-poller", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)

    def is_alive(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def _run(self) -> None:
        publish_counter = self._publish_every
        while not self._stop_event.is_set():
            try:
                snapshot = self._collect()
                if isinstance(snapshot, tuple):
                    snapshot = snapshot[0]
                snapshot = {
                    **snapshot,
                    "source_status": "online",
                    "source_error": None,
                    "last_attempt_at": snapshot.get("ts"),
                }
                self._last_successful_snapshot = dict(snapshot)
                self._on_snapshot(snapshot)
            except Exception as exc:
                logger.log(f"Error en ciclo PVE: {exc}", "PVE/POLL")
                attempted_at = self._collect_failure_ts()
                previous = self._last_successful_snapshot or {}
                snapshot = {
                    **previous,
                    "ts": previous.get("ts") or attempted_at,
                    "node": previous.get("node") or "desconocido",
                    "status": "offline",
                    "source_status": "offline",
                    "source_error": str(exc),
                    "last_attempt_at": attempted_at,
                    "vms": previous.get("vms", []),
                    "missing": previous.get("missing", []),
                    "error": str(exc),
                }
                try:
                    self._on_failure(snapshot)
                except Exception as failure_error:
                    logger.log(
                        f"Error registrando falla PVE: {failure_error}",
                        "PVE/POLL",
                    )
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
