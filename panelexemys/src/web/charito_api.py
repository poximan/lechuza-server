from __future__ import annotations

from typing import Any, Callable

from src.servicios.charito.charito_service import CharitoService


class CharitoApi:
    def __init__(
        self,
        service: CharitoService,
        response: Callable[[Callable[[], dict[str, Any]]], Any],
    ):
        self.service = service
        self.response = response

    def get(self) -> Any:
        return self.response(self.service.get_contract)
