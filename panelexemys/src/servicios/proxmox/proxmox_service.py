from __future__ import annotations

from typing import Any

from src.dao.dao_proxmox_view import ProxmoxViewDao
from src.negocio.proxmox import validate_proxmox_view


class ProxmoxService:
    def __init__(self, client: Any, view_dao: ProxmoxViewDao):
        self.client = client
        self.view_dao = view_dao

    def get_contract(self) -> dict[str, Any]:
        state: dict[str, Any] | None = None
        history: dict[str, Any] | None = None
        state_error: str | None = None
        history_error: str | None = None
        try:
            state = self.client.get_state()
        except Exception as exc:
            state_error = f"{type(exc).__name__}: {exc}"
        try:
            history = self.client.get_history()
        except Exception as exc:
            history_error = f"{type(exc).__name__}: {exc}"
        return {
            "state": state,
            "state_error": state_error,
            "history": history,
            "history_error": history_error,
            "view": self.view_dao.load(),
        }

    def set_view(self, view: str) -> dict[str, Any]:
        validated = validate_proxmox_view(view)
        self.view_dao.save(validated)
        return {"saved": True, "view": validated}
