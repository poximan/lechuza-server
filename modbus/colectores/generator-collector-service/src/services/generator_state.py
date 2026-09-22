import json
import os
import tempfile
import threading
from typing import Any, Dict


class GeneratorStateCache:
    """
    Cache thread-safe para exponer el ultimo estado valido de cada generador.
    """

    def __init__(self, path: str) -> None:
        self._lock = threading.RLock()
        self._path = path
        self._snapshots: Dict[str, Dict[str, Any]] = {}
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as handle:
                loaded = json.load(handle)
            if not isinstance(loaded, dict):
                raise RuntimeError("El estado persistido de generadores debe ser un objeto")
            self._snapshots = {
                str(key): self._normalize_legacy(dict(value))
                for key, value in loaded.items()
                if isinstance(value, dict)
            }

    @staticmethod
    def _normalize_legacy(value: Dict[str, Any]) -> Dict[str, Any]:
        timestamp = value.get("measured_at") or value.get("ts")
        if timestamp and not value.get("measured_at"):
            value["measured_at"] = timestamp
        value.setdefault("last_attempt_at", timestamp)
        value.setdefault("status", "available" if timestamp else "unavailable")
        value.setdefault("error", None)
        return value

    def update(self, key: str, payload: Dict[str, Any]) -> None:
        with self._lock:
            updated = {name: dict(value) for name, value in self._snapshots.items()}
            updated[key] = dict(payload)
            directory = os.path.dirname(self._path)
            os.makedirs(directory, exist_ok=True)
            temporary = None
            try:
                with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=directory, delete=False) as handle:
                    temporary = handle.name
                    json.dump(updated, handle, ensure_ascii=False, indent=2)
                    handle.flush(); os.fsync(handle.fileno())
                os.replace(temporary, self._path)
                self._snapshots = updated
            finally:
                if temporary and os.path.exists(temporary): os.remove(temporary)

    def mark_failure(self, key: str, error: str, attempted_at: str) -> Dict[str, Any]:
        with self._lock:
            current = dict(self._snapshots.get(key, {}))
        failed = {
            **current,
            "edificio": key,
            "status": "stale" if current.get("measured_at") else "unavailable",
            "last_attempt_at": attempted_at,
            "error": error,
        }
        self.update(
            key,
            failed,
        )
        return failed

    def snapshot(self, key: str) -> Dict[str, Any]:
        with self._lock:
            snapshot = self._snapshots.get(key)
            if snapshot is None:
                raise RuntimeError(f"{key} sin lectura valida inicial")
            return dict(snapshot)
