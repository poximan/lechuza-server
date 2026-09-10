from __future__ import annotations

from typing import Any, Callable

from flask import jsonify, request

from src.servicios.reles.reles_service import RelesService


class RelesApi:
    def __init__(
        self,
        service: RelesService,
        require_protected: Callable[[], Any | None],
        response: Callable[[Callable[[], dict[str, Any]]], Any],
    ):
        self.service = service
        self.require_protected = require_protected
        self.response = response

    def get(self) -> Any:
        return self.response(self.service.get_contract)

    def set_observer(self) -> Any:
        denied = self.require_protected()
        if denied is not None:
            return denied
        body = request.get_json(silent=True)
        if not isinstance(body, dict) or not isinstance(body.get("enabled"), bool):
            return jsonify({"error": "enabled debe ser booleano"}), 400
        return self.response(
            lambda: self.service.set_observer(bool(body["enabled"]))
        )

    def disturbances(self, relay_id: int) -> Any:
        return self.response(lambda: self.service.get_disturbances(relay_id))

    def disturbance(self, relay_id: int, record_number: int) -> Any:
        return self.response(lambda: self.service.get_disturbance(relay_id, record_number))

    def clock_snapshot(self, relay_id: int) -> Any:
        return self.response(lambda: self.service.read_clock(relay_id))
