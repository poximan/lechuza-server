import json
import os
import threading
from typing import Any, Dict


class ObserverStateStore:
    """
    Persistencia simple para banderas de observacion (hoy: relés).
    """

    def __init__(self, path: str):
        self._path = path
        self._lock = threading.RLock()
        self._data: Dict[str, Any] = {}
        self._load()

    def _load(self) -> None:
        if not os.path.exists(self._path):
            self._data = {}
            return
        try:
            with open(self._path, "r", encoding="utf-8") as fh:
                content = fh.read().strip()
                self._data = json.loads(content) if content else {}
        except Exception:
            self._data = {}

    def _save(self) -> None:
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        with open(self._path, "w", encoding="utf-8") as fh:
            json.dump(self._data, fh, ensure_ascii=False, indent=2)

    def get_reles_enabled(self) -> bool:
        with self._lock:
            return bool(self._data.get("reles_consultar", False))

    def set_reles_enabled(self, enabled: bool) -> None:
        with self._lock:
            self._data["reles_consultar"] = bool(enabled)
            self._save()
