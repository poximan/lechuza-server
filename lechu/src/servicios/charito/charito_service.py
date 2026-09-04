from __future__ import annotations

from typing import Any


class CharitoService:
    def __init__(self, client: Any):
        self.client = client

    def get_contract(self) -> dict[str, Any]:
        return self.client.get_state()
