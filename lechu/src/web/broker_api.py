from __future__ import annotations

from typing import Any, Callable

from flask import jsonify, request

from src.servicios.broker.broker_service import BrokerService


class BrokerApi:
    def __init__(
        self,
        service: BrokerService,
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

    def set_connection(self) -> Any:
        denied = self.require_protected()
        if denied is not None:
            return denied
        body = request.get_json(silent=True)
        if not isinstance(body, dict) or not isinstance(body.get("enabled"), bool):
            return jsonify({"error": "enabled debe ser booleano"}), 400
        return self.response(
            lambda: self.service.set_connection(bool(body["enabled"]))
        )
