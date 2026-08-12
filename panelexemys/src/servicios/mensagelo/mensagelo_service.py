from __future__ import annotations

from typing import Any

from src.dao.dao_mensagelo_attempts import MensageloAttemptsDao


class MensageloService:
    def __init__(self, dao: MensageloAttemptsDao):
        self.dao = dao

    def get_contract(self) -> dict[str, list[dict[str, Any]]]:
        return {"items": self.dao.latest()}
