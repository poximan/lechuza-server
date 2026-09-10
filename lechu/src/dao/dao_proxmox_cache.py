from __future__ import annotations

from copy import deepcopy
import threading
from typing import Any

from src.dao.lechu_state_store import read_value, write_value


_LOCK = threading.RLock()


class ProxmoxCacheDao:
    """Persiste la última respuesta válida sin depender del servicio PVE."""

    _KEY = "proxmox_cache"
    _RESOURCES = {"state", "history"}

    def load(self) -> dict[str, dict[str, Any] | None]:
        with _LOCK:
            stored = read_value(self._KEY)
            if stored is None:
                return {"state": None, "history": None}
            if not isinstance(stored, dict):
                raise RuntimeError("La caché Proxmox persistida no es un objeto")
            return {
                resource: deepcopy(value) if isinstance(value, dict) else None
                for resource, value in (
                    ("state", stored.get("state")),
                    ("history", stored.get("history")),
                )
            }

    def save(self, resource: str, value: dict[str, Any]) -> None:
        if resource not in self._RESOURCES:
            raise ValueError(f"Recurso Proxmox desconocido: {resource}")
        if not isinstance(value, dict):
            raise ValueError("La respuesta Proxmox debe ser un objeto")
        with _LOCK:
            cached = self.load()
            cached[resource] = deepcopy(value)
            write_value(self._KEY, cached)
