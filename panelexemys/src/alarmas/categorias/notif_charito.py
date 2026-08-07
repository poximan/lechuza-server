from datetime import timedelta
from typing import Any, Callable, Dict, List

from src.logger import Logosaurio
from src.utils import timebox
import config


class NotifCharitoDaemon:
    """
    Supervisa el estado de los demonios administrados por charito-service.
    """

    def __init__(self, logger: Logosaurio, on_condition: Callable[[str, bool], None]):
        self.logger = logger
        self.on_condition = on_condition
        self.daemon_states: Dict[str, Dict[str, Any]] = {}

    def evaluate_condition(self, snapshot: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Retorna una lista de demonios que deben disparar alarma.
        """
        if not isinstance(snapshot, dict):
            return []

        items = snapshot.get("items", []) or []
        if not isinstance(items, list):
            return []

        now = timebox.utc_now()
        min_duration = timedelta(minutes=config.ALARM_MIN_SUSTAINED_DURATION_MINUTES)
        alerts: List[Dict[str, Any]] = []

        for item in items:
            if not isinstance(item, dict):
                continue

            instance_id = str(item.get("instanceId") or "").strip()
            alias = str(item.get("alias") or "").strip()
            if not instance_id:
                if alias:
                    instance_id = alias
                else:
                    continue

            status_raw = str(item.get("status") or "unknown").lower()
            is_online = status_raw == "online"
            self.on_condition(f"charito:{instance_id}", not is_online)
            received_at = item.get("receivedAt")
            data_error = str(item.get("dataError") or "").strip()

            state = self.daemon_states.setdefault(
                instance_id,
                {
                    "start_time": None,
                    "triggered": False,
                    "alias": alias or instance_id,
                    "status": status_raw,
                    "received_at": received_at,
                },
            )
            state["alias"] = alias or instance_id
            state["status"] = status_raw
            state["received_at"] = received_at
            state["data_error"] = data_error

            if not is_online:
                if state["start_time"] is None:
                    state["start_time"] = now
                    self.logger.log(
                        f"Alarma potencial: charo-daemon {state['alias']} en estado '{status_raw}'. Iniciando conteo.",
                        origin="NOTIF/CHARITO",
                    )

                if not state["triggered"] and now - state["start_time"] >= min_duration:
                    state["triggered"] = True
                    alerts.append(
                        {
                            "instance_id": instance_id,
                            "alias": state["alias"],
                            "status": status_raw,
                            "status_display": status_raw.upper(),
                            "received_at": received_at,
                            "data_error": data_error,
                        }
                    )
            else:
                if state["start_time"] is not None:
                    self.logger.log(
                        f"Condicion normal observada: {state['alias']} regreso a ONLINE. Confirmando recuperacion.",
                        origin="NOTIF/CHARITO",
                    )
                state["start_time"] = None
                state["triggered"] = False

        return alerts
