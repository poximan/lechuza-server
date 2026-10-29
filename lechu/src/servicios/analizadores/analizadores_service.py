from typing import Any


class AnalizadoresService:
    def __init__(self, client: Any) -> None:
        self.client = client

    def get_contract(self) -> dict[str, Any]:
        return self.client.get_analyzers()

    def set_observer(self, enabled: bool) -> dict[str, bool]:
        return {"enabled": self.client.set_observer(enabled)}
