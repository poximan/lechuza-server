from __future__ import annotations

from src.utils.paths import (
    load_proxmox_view_preference,
    update_proxmox_view_preference,
)


class ProxmoxViewDao:
    def load(self) -> str:
        return load_proxmox_view_preference("historico")

    def save(self, view: str) -> None:
        if not update_proxmox_view_preference(view):
            raise RuntimeError("no se pudo persistir la vista de Proxmox")
