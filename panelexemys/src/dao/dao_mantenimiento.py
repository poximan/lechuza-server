from __future__ import annotations

import json
from pathlib import Path
from typing import Any


MANTENIMIENTO_DATA_PATH = Path(__file__).resolve().with_name("mantenimiento_data.json")


class MantenimientoDao:
    def __init__(self, source_path: Path = MANTENIMIENTO_DATA_PATH):
        self.source_path = source_path

    def load_source(self) -> dict[str, Any]:
        try:
            payload = json.loads(self.source_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"El catalogo de mantenimiento no contiene JSON valido: {self.source_path}"
            ) from exc
        if not isinstance(payload, dict):
            raise ValueError("El catalogo de mantenimiento debe ser un objeto JSON")
        return payload
