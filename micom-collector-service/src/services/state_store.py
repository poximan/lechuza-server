import json
import os
import tempfile
import threading
from typing import Any


class ObserverStateStore:
    """Persistencia atomica de banderas operativas del observador."""

    def __init__(self, path: str):
        self._path = path
        self._lock = threading.RLock()
        self._data: dict[str, Any] = {"reles_consultar": False}
        self._load()

    def _load(self) -> None:
        if not os.path.exists(self._path):
            return
        try:
            with open(self._path, "r", encoding="utf-8") as handle:
                loaded = json.load(handle)
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(
                f"No se pudo leer el estado operativo {self._path}: {exc}"
            ) from exc

        if not isinstance(loaded, dict) or not isinstance(loaded.get("reles_consultar"), bool):
            raise RuntimeError(
                f"Contrato invalido en {self._path}: reles_consultar debe ser booleano"
            )
        self._data = loaded

    def _save(self) -> None:
        directory = os.path.dirname(self._path)
        os.makedirs(directory, exist_ok=True)
        temporary_path: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=directory,
                prefix="modbus-collector-state-",
                suffix=".tmp",
                delete=False,
            ) as handle:
                temporary_path = handle.name
                json.dump(self._data, handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, self._path)
        except OSError as exc:
            if temporary_path and os.path.exists(temporary_path):
                os.remove(temporary_path)
            raise RuntimeError(
                f"No se pudo guardar el estado operativo {self._path}: {exc}"
            ) from exc

    def get_reles_enabled(self) -> bool:
        with self._lock:
            return bool(self._data["reles_consultar"])

    def set_reles_enabled(self, enabled: bool) -> None:
        with self._lock:
            if self._data["reles_consultar"] == enabled:
                return
            self._data["reles_consultar"] = enabled
            self._save()
