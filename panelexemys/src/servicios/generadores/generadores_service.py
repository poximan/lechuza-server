from __future__ import annotations

from typing import Any, Callable

from src.negocio.generadores import build_generator_contract


class GeneradoresService:
    def __init__(self, modbus_client: Any):
        self.modbus_client = modbus_client

    @staticmethod
    def _load_source(operation: Callable[[], dict[str, Any]]) -> dict[str, Any]:
        try:
            return operation()
        except Exception as exc:
            return {
                "interruptor_linea": {"estado": "desconocido", "bit": None},
                "interruptor_grupo": {"estado": "desconocido", "bit": None},
                "error": f"{type(exc).__name__}: {exc}",
            }

    def get_contract(self) -> dict[str, Any]:
        return {
            "estivariz": build_generator_contract(
                self._load_source(
                    self.modbus_client.get_ge_edif_estivariz_status
                ),
                "generadores.estivariz",
            ),
            "fontana": build_generator_contract(
                self._load_source(
                    self.modbus_client.get_ge_edif_fontana_status
                ),
                "generadores.fontana",
            ),
        }
