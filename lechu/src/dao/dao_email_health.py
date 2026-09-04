from __future__ import annotations

from typing import Any

from src.dao.lechu_state_store import read_value, write_value


class EmailHealthDao:
    def load(self) -> dict[str, Any]:
        health = read_value("email_health")
        if not isinstance(health, dict):
            raise ValueError("El estado persistido no contiene email_health valido")
        return health

    def save(self, health: dict[str, Any]) -> None:
        write_value("email_health", health)
