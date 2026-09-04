from __future__ import annotations

from typing import Any, Callable

from src.servicios.email.email_service import EmailService


class EmailApi:
    def __init__(
        self,
        service: EmailService,
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

    def send_test(self) -> Any:
        denied = self.require_protected()
        if denied is not None:
            return denied
        return self.response(self.service.send_test)
