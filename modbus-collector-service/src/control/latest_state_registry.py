import threading


class LatestStateRegistry:
    """Mantiene el ultimo estado conocido sin consultar SQLite en cada lectura."""

    def __init__(self, initial_states: dict[int, int]) -> None:
        self._lock = threading.RLock()
        self._states = {int(key): int(value) for key, value in initial_states.items()}

    def get(self, grd_id: int) -> int | None:
        with self._lock:
            return self._states.get(int(grd_id))

    def update(self, grd_id: int, connected: int) -> None:
        with self._lock:
            self._states[int(grd_id)] = int(connected)

