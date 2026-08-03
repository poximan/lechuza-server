from collections import deque
import threading


class BoundedKeyRegistry:
    """Recuerda una cantidad acotada de claves para evitar logs repetidos."""

    def __init__(self, capacity: int) -> None:
        if capacity <= 0:
            raise ValueError("capacity debe ser mayor que cero")
        self._capacity = capacity
        self._keys: set[str] = set()
        self._order: deque[str] = deque()
        self._lock = threading.Lock()

    def add_if_new(self, key: str) -> bool:
        with self._lock:
            if key in self._keys:
                return False
            if len(self._order) >= self._capacity:
                expired = self._order.popleft()
                self._keys.discard(expired)
            self._keys.add(key)
            self._order.append(key)
            return True

