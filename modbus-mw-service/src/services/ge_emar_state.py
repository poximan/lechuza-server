import threading
from typing import Dict

from src.utils import timebox


class GeEmarStateCache:
    """
    Cache simple y thread-safe para exponer el ultimo estado del GE.
    El payload sigue el mismo formato que MQTT: {"estado": "...", "ts": "..."}.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._snapshot: Dict[str, str] = {
            "estado": "desconocido",
            "ts": timebox.utc_iso(),
        }

    def update(self, payload: Dict[str, str]) -> None:
        with self._lock:
            self._snapshot = dict(payload)

    def snapshot(self) -> Dict[str, str]:
        with self._lock:
            return dict(self._snapshot)
