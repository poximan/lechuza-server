from __future__ import annotations

from typing import Any, Callable

from src.servicios.generadores.generadores_service import GeneradoresService


class GeneradoresApi:
    def __init__(
        self,
        service: GeneradoresService,
        response: Callable[[Callable[[], dict[str, Any]]], Any],
    ):
        self.service = service
        self.response = response

    def get(self) -> Any:
        return self.response(self.service.get_contract)
