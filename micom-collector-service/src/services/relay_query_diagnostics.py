import threading
from collections import deque
from copy import deepcopy


class RelayQueryDiagnostics:
    """Resume las consultas fisicas del lector para la vista de reles."""

    def __init__(self):
        self._state_lock = threading.RLock()
        self._recent_queries = {}

    def record(self, event: dict) -> None:
        relay_id = int(event["relay_id"])
        with self._state_lock:
            history = self._recent_queries.setdefault(relay_id, deque(maxlen=6))
            history.appendleft(deepcopy(event))

    def get_query_snapshot(self, relay_id: int) -> list[dict]:
        with self._state_lock:
            return deepcopy(list(self._recent_queries.get(relay_id, ())))

    def reset(self):
        with self._state_lock:
            self._recent_queries.clear()
