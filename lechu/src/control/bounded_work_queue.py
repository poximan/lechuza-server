import queue
import threading
from typing import Generic, TypeVar


T = TypeVar("T")


class BoundedWorkQueue(Generic[T]):
    """Cola acotada con rechazo explicito y telemetria minima."""

    def __init__(self, maxsize: int) -> None:
        if maxsize <= 0:
            raise ValueError("maxsize debe ser mayor que cero")
        self._queue: queue.Queue[T] = queue.Queue(maxsize=maxsize)
        self._lock = threading.Lock()
        self._rejected = 0

    def try_put(self, item: T) -> bool:
        try:
            self._queue.put_nowait(item)
            return True
        except queue.Full:
            with self._lock:
                self._rejected += 1
            return False

    def get(self) -> T:
        return self._queue.get()

    def task_done(self) -> None:
        self._queue.task_done()

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            rejected = self._rejected
        return {
            "depth": self._queue.qsize(),
            "capacity": self._queue.maxsize,
            "rejected": rejected,
        }

