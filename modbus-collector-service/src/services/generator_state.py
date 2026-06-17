import threading
from typing import Any, Dict


class GeneratorStateCache:
    """
    Cache thread-safe para exponer el ultimo estado valido de cada generador.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._snapshots: Dict[str, Dict[str, Any]] = {}

    def update(self, key: str, payload: Dict[str, Any]) -> None:
        with self._lock:
            self._snapshots[key] = dict(payload)

    def snapshot(self, key: str) -> Dict[str, Any]:
        with self._lock:
            snapshot = self._snapshots.get(key)
            if snapshot is None:
                raise RuntimeError(f"{key} sin lectura valida inicial")
            return dict(snapshot)
