import json
import os
import tempfile
import threading


class JanitzaObserverStateStore:
    """Conserva el estado global del observador sin modificar las mediciones."""

    def __init__(self, path: str) -> None:
        self.path = path
        self.lock = threading.RLock()
        # El primer inicio conserva la lectura automatica que ya tenia Janitza.
        self._enabled = True
        try:
            with open(path, "r", encoding="utf-8") as handle:
                loaded = json.load(handle)
        except FileNotFoundError:
            return
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Estado del observador Janitza invalido: {path}") from exc
        if not isinstance(loaded, dict) or type(loaded.get("enabled")) is not bool:
            raise RuntimeError(f"Estado del observador Janitza invalido: {path}")
        self._enabled = loaded["enabled"]

    def is_enabled(self) -> bool:
        with self.lock:
            return self._enabled

    def set_enabled(self, enabled: bool) -> bool:
        if type(enabled) is not bool:
            raise ValueError("enabled debe ser booleano")
        with self.lock:
            directory = os.path.dirname(os.path.abspath(self.path))
            os.makedirs(directory, exist_ok=True)
            temporary = None
            try:
                with tempfile.NamedTemporaryFile(
                    "w", encoding="utf-8", dir=directory, delete=False
                ) as handle:
                    temporary = handle.name
                    json.dump({"enabled": enabled}, handle)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temporary, self.path)
                self._enabled = enabled
            finally:
                if temporary and os.path.exists(temporary):
                    os.remove(temporary)
            return self._enabled
