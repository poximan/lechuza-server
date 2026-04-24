from datetime import timedelta
from typing import Dict, Any
from src.logger import Logosaurio
from src.utils import timebox
from src.web.clients.router_client import router_client
import config

class NotifModem:
    def __init__(self, logger: Logosaurio):
        self.logger = logger
        self.state: Dict[str, Any] = {
            'start_time': None,
            'triggered': False,
            'description': "Router telef. puerto de escucha cerrado"
        }
    
    def evaluate_condition(self) -> bool:
        """
        Evalúa la condición de alarma del módem.
        Retorna True si la alarma debe ser disparada, False en caso contrario.
        """
        modem_status = self._get_modem_status()
        is_disconnected = modem_status == "cerrado"

        if is_disconnected:
            if self.state['start_time'] is None:
                self.state['start_time'] = timebox.utc_now()
                self.logger.log("Alarma potencial: Router Modem con puerto cerrado. Iniciando conteo.", origin="NOTIF/MODEM")
            
            sustained_duration = timebox.utc_now() - self.state['start_time']
            min_duration = timedelta(minutes=config.ALARM_MIN_SUSTAINED_DURATION_MINUTES)
            
            if sustained_duration >= min_duration and not self.state['triggered']:
                self.state['triggered'] = True
                return True
        else:
            if self.state['start_time'] is not None:
                self.logger.log("Alarma de router modem resuelta (puerto abierto).", origin="NOTIF/MODEM")
            self.state['start_time'] = None
            self.state['triggered'] = False

        return False

    def _get_modem_status(self) -> str:
        """Consulta router-telef-service para conocer el estado."""
        try:
            status = router_client.get_status()
            return str(status.get("state", "cerrado"))
        except Exception as e:
            self.logger.log(f"ERROR consultando router-telef-service: {e}. Asumiendo puerto cerrado.", origin="NOTIF/MODEM")
            return "cerrado"
