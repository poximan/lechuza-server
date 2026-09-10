from collections import deque
from contextlib import contextmanager
from copy import deepcopy
import threading

from src.utils import timebox


class ModbusChannelQueue:
    """FIFO por endpoint fisico; mantiene una sola consulta en vuelo."""

    def __init__(self, endpoint: str):
        self.endpoint = endpoint
        self._condition = threading.Condition()
        self._pending = deque()
        self._active = None
        self._sequence = 0
        self._completed = 0
        self._failed = 0
        self._attempts = 0
        self._samples = deque(maxlen=4096)
        self._created = timebox.monotonic()

    @contextmanager
    def dispatch(self, description, cancelled, heartbeat):
        with self._condition:
            self._sequence += 1
            request = {
                **description, "id": self._sequence,
                "queued_at": timebox.utc_iso(), "attempt": 0,
            }
            self._pending.append(request)
            try:
                while self._active is not None or self._pending[0] is not request:
                    if cancelled():
                        raise RuntimeError("Consulta Modbus cancelada durante el apagado")
                    self._condition.wait(timeout=1)
                    heartbeat()
                if cancelled():
                    raise RuntimeError("Consulta Modbus cancelada durante el apagado")
                self._pending.popleft()
                request["started_at"] = timebox.utc_iso()
                request["started_monotonic"] = timebox.monotonic()
                self._active = request
            except BaseException:
                if request in self._pending:
                    self._pending.remove(request)
                self._condition.notify_all()
                raise
        succeeded = False
        try:
            yield request
            succeeded = bool(request.get("succeeded"))
        finally:
            with self._condition:
                end = timebox.monotonic()
                self._samples.append((request["started_monotonic"], end, succeeded))
                self._completed += 1
                self._failed += int(not succeeded)
                self._active = None
                self._condition.notify_all()
            heartbeat()

    def record_attempt(self, request, attempt):
        with self._condition:
            request["attempt"] = attempt
            self._attempts += 1

    def snapshot(self):
        with self._condition:
            now = timebox.monotonic()
            window_start = max(self._created, now - 60)
            samples = [s for s in self._samples if s[1] > window_start]
            busy = sum(end - max(start, window_start) for start, end, _ in samples)
            if self._active:
                busy += now - max(self._active["started_monotonic"], window_start)
            active = deepcopy(self._active)
            if active:
                active["elapsed_ms"] = round((now - active.pop("started_monotonic")) * 1000, 1)
                active.pop("succeeded", None)
            return {
                "endpoint": self.endpoint,
                "window_seconds": 60,
                "busy_percent": round(100 * busy / max(now - window_start, 0.001), 2),
                "completed": self._completed,
                "failed": self._failed,
                "attempts": self._attempts,
                "average_duration_ms": round(sum(end - start for start, end, _ in samples) * 1000 / len(samples), 1) if samples else None,
                "current": active,
                "queue_depth": len(self._pending),
                "next": deepcopy(list(self._pending)),
            }
