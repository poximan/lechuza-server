from __future__ import annotations

from src.dao.lechu_state_store import read_value, write_value


_VALID_VIEWS = {"vivo", "historico"}


class ProxmoxViewDao:
    def load(self) -> str:
        stored = read_value("proxmox_view")
        if stored is None:
            return "historico"
        if stored not in _VALID_VIEWS:
            raise ValueError("proxmox_view persistido fuera de contrato")
        return str(stored)

    def save(self, view: str) -> None:
        if view not in _VALID_VIEWS:
            raise ValueError("view debe ser 'vivo' o 'historico'")
        write_value("proxmox_view", view)
