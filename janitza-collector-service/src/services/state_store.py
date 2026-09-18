import json
import os
import tempfile
import threading
from copy import deepcopy

class JanitzaStateStore:
    def __init__(self, path: str):
        self.path = path
        self.lock = threading.RLock()
        self.data = {}
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as handle:
                loaded = json.load(handle)
            if not isinstance(loaded, dict):
                raise RuntimeError("Estado Janitza invalido")
            self.data = loaded
    def update(self, key: str, payload: dict):
        with self.lock:
            updated = deepcopy(self.data)
            updated[key] = deepcopy(payload)
            directory = os.path.dirname(self.path)
            os.makedirs(directory, exist_ok=True)
            temporary = None
            try:
                with tempfile.NamedTemporaryFile(
                    "w", encoding="utf-8", dir=directory, delete=False
                ) as handle:
                    temporary = handle.name
                    json.dump(updated, handle, ensure_ascii=False, indent=2)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temporary, self.path)
                self.data = updated
            finally:
                if temporary and os.path.exists(temporary):
                    os.remove(temporary)
    def snapshot(self):
        with self.lock:
            return deepcopy(self.data)
