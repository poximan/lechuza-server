from typing import Any, Callable

from flask import jsonify, request

from src.servicios.analizadores.analizadores_service import AnalizadoresService


class AnalizadoresApi:
    def __init__(
        self,
        service: AnalizadoresService,
        require_protected: Callable[[], Any | None],
        response: Callable[[Callable[[], dict[str, Any]]], Any],
    ) -> None:
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
        if not isinstance(body, dict) or type(body.get("enabled")) is not bool:
            return jsonify({"error": "enabled debe ser booleano"}), 400
        return self.response(lambda: self.service.set_observer(body["enabled"]))
