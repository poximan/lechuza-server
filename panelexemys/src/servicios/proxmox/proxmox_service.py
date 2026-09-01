from __future__ import annotations

import threading
import time
from copy import deepcopy
from typing import Any

from src.dao.dao_proxmox_view import ProxmoxViewDao
from src.negocio.proxmox import validate_proxmox_view


class ProxmoxService:
    STATE_REFRESH_SECONDS = 10
    HISTORY_REFRESH_SECONDS = 120

    def __init__(self, client: Any, view_dao: ProxmoxViewDao):
        self.client = client
        self.view_dao = view_dao
        self._lock = threading.RLock()
        self._values: dict[str, dict[str, Any] | None] = {
            "state": None,
            "history": None,
        }
        self._errors: dict[str, str | None] = {
            "state": None,
            "history": None,
        }
        self._last_attempts: dict[str, float | None] = {
            "state": None,
            "history": None,
        }
        self._refreshing: set[str] = set()
        self._schedule_refresh("state")
        self._schedule_refresh("history")

    def get_contract(self) -> dict[str, Any]:
        self._schedule_refresh("state")
        self._schedule_refresh("history")
        with self._lock:
            state = deepcopy(self._values["state"])
            history = deepcopy(self._values["history"])
            state_error = self._errors["state"]
            history_error = self._errors["history"]
            refreshing = sorted(self._refreshing)
        return {
            "state": state,
            "state_error": state_error,
            "history": history,
            "history_error": history_error,
            "refreshing": refreshing,
            "view": self.view_dao.load(),
        }

    def _schedule_refresh(self, resource: str) -> None:
        interval = (
            self.STATE_REFRESH_SECONDS
            if resource == "state"
            else self.HISTORY_REFRESH_SECONDS
        )
        with self._lock:
            last_attempt = self._last_attempts[resource]
            if resource in self._refreshing:
                return
            if last_attempt is not None and time.monotonic() - last_attempt < interval:
                return
            self._refreshing.add(resource)
        threading.Thread(
            target=self._refresh,
            args=(resource,),
            daemon=True,
            name=f"proxmox-{resource}-refresh",
        ).start()

    def _refresh(self, resource: str) -> None:
        operation = (
            self.client.get_state
            if resource == "state"
            else self.client.get_history
        )
        value: dict[str, Any] | None = None
        error: str | None = None
        try:
            value = operation()
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
        with self._lock:
            if value is not None:
                self._values[resource] = value
            self._errors[resource] = error
            self._last_attempts[resource] = time.monotonic()
            self._refreshing.discard(resource)

    def set_view(self, view: str) -> dict[str, Any]:
        validated = validate_proxmox_view(view)
        self.view_dao.save(validated)
        return {"saved": True, "view": validated}
