import threading


class LatestStateRegistry:
    """Mantiene estados confirmados y fallos transitorios de lectura."""

    def __init__(self, initial_states: dict[int, int]) -> None:
        self._lock = threading.RLock()
        self._states = {int(key): int(value) for key, value in initial_states.items()}
        self._failures: dict[int, dict[str, int | str]] = {}

    def get(self, grd_id: int) -> int | None:
        with self._lock:
            return self._states.get(int(grd_id))

    def update(self, grd_id: int, connected: int) -> None:
        with self._lock:
            self._states[int(grd_id)] = int(connected)

    def mark_read_success(self, grd_id: int) -> None:
        with self._lock:
            self._failures.pop(int(grd_id), None)

    def mark_read_failure(
        self,
        grd_id: int,
        timestamp: str,
        *,
        confirmable: bool = True,
    ) -> int:
        with self._lock:
            key = int(grd_id)
            current = self._failures.get(key)
            if current is None:
                current = {
                    "consecutive_failures": 0,
                    "confirmable_failures": 0,
                    "reason": (
                        "lectura_dispositivo"
                        if confirmable
                        else "gateway_no_disponible"
                    ),
                    "since": timestamp,
                }
                self._failures[key] = current
            current["consecutive_failures"] = (
                int(current["consecutive_failures"]) + 1
            )
            if confirmable:
                current["confirmable_failures"] = int(current["confirmable_failures"]) + 1
                current["reason"] = "lectura_dispositivo"
            else:
                current["confirmable_failures"] = 0
                current["reason"] = "gateway_no_disponible"
            return int(current["confirmable_failures"])

    def unavailable_snapshot(self) -> dict[int, dict[str, int | str]]:
        with self._lock:
            return {
                grd_id: dict(details)
                for grd_id, details in self._failures.items()
            }
