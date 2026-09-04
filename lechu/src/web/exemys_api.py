from __future__ import annotations

from typing import Any, Callable

from flask import jsonify, request

from src.servicios.exemys.exemys_service import ExemysService


class ExemysApi:
    def __init__(
        self,
        service: ExemysService,
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

    def get_grd_detail(self) -> Any:
        denied = self.require_protected()
        if denied is not None:
            return denied
        try:
            grd_id = int(request.args["grd_id"])
            window = str(request.args.get("window", "1sem"))
            page = int(request.args.get("page", "0"))
        except (KeyError, TypeError, ValueError):
            return jsonify({"error": "grd_id, window y page deben ser validos"}), 400
        if window not in {"1sem", "1mes", "todo"} or page < 0:
            return jsonify({"error": "window o page fuera de contrato"}), 400
        return self.response(
            lambda: self.service.get_grd_detail(grd_id, window, page)
        )
