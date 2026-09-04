from __future__ import annotations

from typing import Any, Callable

from flask import jsonify, request

from src.negocio.proxmox import PROXMOX_VIEWS
from src.servicios.proxmox.proxmox_service import ProxmoxService


class ProxmoxApi:
    def __init__(
        self,
        service: ProxmoxService,
        require_protected: Callable[[], Any | None],
        response: Callable[[Callable[[], dict[str, Any]]], Any],
    ):
        self.service = service
        self.require_protected = require_protected
        self.response = response

    def get(self) -> Any:
        denied = self.require_protected()
        if denied is not None:
            return denied
        return self.response(self.service.get_contract)

    def set_view(self) -> Any:
        denied = self.require_protected()
        if denied is not None:
            return denied
        body = request.get_json(silent=True)
        if not isinstance(body, dict) or body.get("view") not in PROXMOX_VIEWS:
            return jsonify({"error": "view debe ser 'vivo' o 'historico'"}), 400
        return self.response(lambda: self.service.set_view(str(body["view"])))
