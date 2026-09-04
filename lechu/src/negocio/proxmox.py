from __future__ import annotations


PROXMOX_VIEWS = {"vivo", "historico"}


def validate_proxmox_view(view: str) -> str:
    if view not in PROXMOX_VIEWS:
        raise ValueError("view debe ser 'vivo' o 'historico'")
    return view
