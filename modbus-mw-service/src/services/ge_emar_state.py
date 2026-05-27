import threading
from typing import Any, Dict


class GeEmarStateCache:
    """
    Cache simple y thread-safe para exponer el ultimo estado de interruptores GE.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._snapshot: Dict[str, Any] | None = None

    def update(self, payload: Dict[str, Any]) -> None:
        with self._lock:
            self._snapshot = dict(payload)

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            if self._snapshot is None:
                raise RuntimeError("GE_EMAR sin lectura valida inicial")
            return dict(self._snapshot)
