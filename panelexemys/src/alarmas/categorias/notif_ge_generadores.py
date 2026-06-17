from datetime import timedelta
from typing import Any, List

from src.logger import Logosaurio
from src.utils import timebox


class NotifGeGeneradores:
    """
    Supervisa interruptores lado grupo de los edificios con GE.
    """

    def __init__(
        self,
        logger: Logosaurio,
        buildings: list[dict[str, Any]],
        min_duration_seconds: int = 60,
    ):
        self.logger = logger
        self.buildings = buildings
        self.min_duration = timedelta(seconds=max(1, min_duration_seconds))
        self._sustained_states: dict[str, dict[str, Any]] = {}
        self._last_generator_bits: dict[str, int] = {}

    def evaluate(self) -> List[dict[str, str]]:
        alerts: List[dict[str, str]] = []
        for building in self.buildings:
            status = self._get_status(building)
            sustained_alert = self._evaluate_sustained_closed(building, status)
            if sustained_alert is not None:
                alerts.append(sustained_alert)

            change_alert = self._evaluate_generator_state_change(building, status)
            if change_alert is not None:
                alerts.append(change_alert)

        return alerts

    def _evaluate_sustained_closed(self, building: dict[str, Any], status: dict[str, Any]) -> dict[str, str] | None:
        if not bool(building.get("sustained_closed_alarm", False)):
            return None

        key = str(building["key"])
        label = str(building["label"])
        estado = self._generator_estado(status)
        state = self._sustained_states.setdefault(
            key,
            {
                "start_time": None,
                "triggered": False,
            },
        )

        if estado != "cerrado":
            if state["start_time"] is not None or state["triggered"]:
                self.logger.log(f"{key}: interruptor de grupo abierto, se reinicia conteo.", origin="ALRM/GE")
            state["start_time"] = None
            state["triggered"] = False
            return None

        now = timebox.utc_now()
        if state["start_time"] is None:
            state["start_time"] = now
            self.logger.log(f"{key}: interruptor de grupo cerrado, iniciando conteo.", origin="ALRM/GE")
            return None

        if not state["triggered"] and (now - state["start_time"]) >= self.min_duration:
            state["triggered"] = True
            self.logger.log(f"{key}: condicion sostenida, activar alarma.", origin="ALRM/GE")
            return {
                "subject": f"{label} interruptor GE cerrado",
                "body": (
                    f"El interruptor de grupo electrogeno de {label} permanece cerrado "
                    "por mas de 1 minuto."
                ),
            }

        return None

    def _evaluate_generator_state_change(self, building: dict[str, Any], status: dict[str, Any]) -> dict[str, str] | None:
        key = str(building["key"])
        label = str(building["label"])
        interruptor_grupo = status.get("interruptor_grupo") if isinstance(status, dict) else None
        if not isinstance(interruptor_grupo, dict):
            self.logger.log(f"{key}: respuesta GE sin interruptor_grupo.", origin="ALRM/GE")
            return None

        bit = self._parse_bit(interruptor_grupo.get("bit"))
        if bit is None:
            self.logger.log(f"{key}: interruptor de grupo sin bit valido.", origin="ALRM/GE")
            return None

        previous = self._last_generator_bits.get(key)
        self._last_generator_bits[key] = bit
        if previous is None or previous == bit:
            return None

        estado = self._estado_from_bit(bit)
        prev_estado = self._estado_from_bit(previous)
        self.logger.log(
            f"{key}: interruptor de grupo cambio de {prev_estado} a {estado}.",
            origin="ALRM/GE",
        )
        return {
            "subject": f"{label} interruptor GE {estado}",
            "body": (
                f"El interruptor lado grupo electrogeno de {label} cambio de "
                f"{prev_estado} a {estado}."
            ),
        }

    def _get_status(self, building: dict[str, Any]) -> dict[str, Any]:
        key = str(building["key"])
        fetch_status = building.get("fetch_status")
        if not callable(fetch_status):
            self.logger.log(f"{key}: fetch_status GE no configurado.", origin="ALRM/GE")
            return {}
        try:
            status = fetch_status()
            if isinstance(status, dict):
                return status
            self.logger.log(f"{key}: respuesta GE invalida.", origin="ALRM/GE")
        except Exception as exc:
            self.logger.log(f"{key}: error consultando estado GE: {exc}", origin="ALRM/GE")
        return {}

    @staticmethod
    def _generator_estado(status: dict[str, Any]) -> str:
        interruptor_grupo = status.get("interruptor_grupo") if isinstance(status, dict) else None
        if not isinstance(interruptor_grupo, dict):
            return "desconocido"
        return str(interruptor_grupo.get("estado", "desconocido")).strip().lower()

    @staticmethod
    def _parse_bit(value: Any) -> int | None:
        try:
            bit = int(value)
        except (TypeError, ValueError):
            return None
        if bit not in (0, 1):
            return None
        return bit

    @staticmethod
    def _estado_from_bit(bit: int) -> str:
        return "cerrado" if bit == 1 else "abierto"
