from __future__ import annotations

from typing import Any, Callable

from src.servicios.mantenimiento.mantenimiento_service import MantenimientoService


class MantenimientoApi:
    def __init__(
        self,
        service: MantenimientoService,
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
