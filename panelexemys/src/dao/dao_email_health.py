from __future__ import annotations

from typing import Any

from src.utils.paths import load_observar


class EmailHealthDao:
    def load(self) -> dict[str, Any]:
        data = load_observar()
        health = data.get("server_email_estado")
        if not isinstance(health, dict):
            raise ValueError("observar.json no contiene server_email_estado valido")
        return health
