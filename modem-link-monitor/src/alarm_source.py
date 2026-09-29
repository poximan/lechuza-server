from pathlib import Path

from alarm_generator import AlarmDefinition, AlarmGeneratorOutbox

from . import config


class ModemAlarmSource:
    def __init__(self) -> None:
        self._healthy_observations = 0
        self.outbox = AlarmGeneratorOutbox(
            "modem-link-monitor",
            Path(config.DATA_DIR) / "alarm-events.json",
            activation_seconds=1200,
            recovery_seconds=20,
        )
        self.outbox.register(
            AlarmDefinition(
                alarm_key="modem:link",
                title="Router telefonico no alcanzable",
                category="modem",
                expected_clearance_minutes=60,
            )
        )

    def observe(self, state: str, connectivity_percentage: float | None, timestamp: str) -> None:
        if state == "desconocido":
            self._healthy_observations = 0
            return
        if state not in {"abierto", "cerrado"}:
            raise ValueError(f"Estado TCP fuera de contrato: {state}")

        current = next(
            item["condition_active"]
            for item in self.outbox.catalog_snapshot()["alarms"]
            if item["alarm_key"] == "modem:link"
        )
        if state == "cerrado":
            self._healthy_observations = 0
            active = True
            subject = "Router telef. puerto de escucha cerrado"
            body = "El test externo informa que el puerto del router telefonico esta cerrado."
        elif connectivity_percentage is None:
            self._healthy_observations = 0
            return
        elif connectivity_percentage < config.GLOBAL_THRESHOLD_ROJO:
            self._healthy_observations = 0
            if current is not True:
                return
            active = True
            subject = "Router telefonico sin conectividad confirmada"
            body = (
                "El puerto externo responde, pero la conectividad global Exemys "
                f"sigue en zona roja ({connectivity_percentage:.2f}%)."
            )
        else:
            if current is False:
                return
            self._healthy_observations += 1
            if self._healthy_observations < 2:
                return
            active = False
            subject = "Router telefonico recuperado"
            body = (
                "El puerto externo responde en dos chequeos consecutivos y la "
                f"conectividad global Exemys salio de zona roja ({connectivity_percentage:.2f}%)."
            )
        self.outbox.observe(
            "modem:link",
            active,
            timestamp,
            subject=subject,
            body=body,
        )
