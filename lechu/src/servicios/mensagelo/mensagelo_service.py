from __future__ import annotations

from typing import Any

import config
from src.servicios.email.mensagelo_client import MensageloClient


class MensageloService:
    def __init__(self):
        self.client = MensageloClient(
            config.MENSAGELO_BASE_URL, config.MENSAGELO_API_KEY,
            config.MENSAGELO_TIMEOUT_SECONDS, config.MENSAGELO_MAX_RETRIES,
            config.MENSAGELO_BACKOFF_INITIAL, config.MENSAGELO_BACKOFF_MAX,
        )

    def get_contract(self) -> dict[str, list[dict[str, Any]]]:
        return {"items": self.client.list_messages()}
