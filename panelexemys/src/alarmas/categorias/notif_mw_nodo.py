from datetime import timedelta
from typing import Dict, Any, List
from src.logger import Logosaurio
from src.utils import timebox
import config

class NotifMwNodo:
    def __init__(self, logger: Logosaurio, excluded_grd_ids: set):
        self.logger = logger
        self.individual_grd_alarm_states: Dict[int, Dict[str, Any]] = {}
        self.excluded_grd_ids: set = excluded_grd_ids

    def evaluate_condition(self, current_percentage: float, disconnected_grds: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Evalúa las condiciones de alarma para GRDs individuales.
        Retorna una lista de GRDs para los que la alarma debe ser disparada.
        """
        grds_to_trigger = []
        current_disconnected_ids = {grd['id_grd'] for grd in disconnected_grds}
        
        # Limpiar estados de GRDs reconectados o no aplicables
        grds_to_remove = [
            grd_id
            for grd_id in list(self.individual_grd_alarm_states.keys())
            if grd_id not in current_disconnected_ids
        ]
               
        for grd_id in grds_to_remove:
            if grd_id in self.individual_grd_alarm_states:
                self.logger.log(
                    f"Alarma individual para GRD {grd_id} ({self.individual_grd_alarm_states[grd_id]['description']}) resuelta.",
                    origin="NOTIF/NODO"
                )
                del self.individual_grd_alarm_states[grd_id]
        
        # Evaluar nuevos estados de desconexion
        for grd_info in disconnected_grds:
            grd_id = grd_info['id_grd']
            grd_description = grd_info['description']

            if current_percentage >= config.GLOBAL_THRESHOLD_ROJO and grd_id not in self.excluded_grd_ids:
                if grd_id not in self.individual_grd_alarm_states:
                    self.individual_grd_alarm_states[grd_id] = {
                        'start_time': timebox.utc_now(),
                        'triggered': False,
                        'description': grd_description
                    }
                    self.logger.log(
                        f"Alarma potencial: GRD {grd_id} ({grd_description}) desconectado. Iniciando conteo.", 
                        origin="NOTIF/NODO"
                    )
                else:
                    sustained_duration = timebox.utc_now() - self.individual_grd_alarm_states[grd_id]['start_time']
                    min_duration = timedelta(minutes=config.ALARM_MIN_SUSTAINED_DURATION_MINUTES)

                    if sustained_duration >= min_duration and not self.individual_grd_alarm_states[grd_id]['triggered']:
                        self.individual_grd_alarm_states[grd_id]['triggered'] = True
                        grds_to_trigger.append(self.individual_grd_alarm_states[grd_id])

        return grds_to_trigger
