from datetime import timedelta
from typing import Optional

from src.logger import Logosaurio
from src.utils import timebox


class NotifGeEmar:
    """
    Genera una alarma cuando el interruptor de grupo permanece cerrado.
    """

    def __init__(self, logger: Logosaurio, ge_client, min_duration_seconds: int = 60):
        self.logger = logger
        self.ge_client = ge_client
        self.min_duration = timedelta(seconds=max(1, min_duration_seconds))
        self._start_time: Optional[timebox.datetime] = None
        self._triggered = False

    def evaluate_condition(self) -> bool:
        try:
            status = self.ge_client.get_status()
            interruptor_grupo = status.get("interruptor_grupo") or {}
            estado = str(interruptor_grupo.get("estado", "desconocido")).strip().lower()
        except Exception as exc:
            self.logger.log(f"GE_EMAR: error consultando estado: {exc}", origin="ALRM/GE")
            estado = "desconocido"

        if estado != "cerrado":
            if self._start_time is not None or self._triggered:
                self.logger.log("GE_EMAR: interruptor de grupo abierto, se reinicia conteo.", origin="ALRM/GE")
            self._start_time = None
            self._triggered = False
            return False

        now = timebox.utc_now()
        if self._start_time is None:
            self._start_time = now
            self.logger.log("GE_EMAR: interruptor de grupo cerrado, iniciando conteo.", origin="ALRM/GE")
            return False

        if not self._triggered and (now - self._start_time) >= self.min_duration:
            self._triggered = True
            self.logger.log("GE_EMAR: condicion sostenida, activar alarma.", origin="ALRM/GE")
            return True

        return False
