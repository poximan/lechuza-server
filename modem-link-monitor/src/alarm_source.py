from pathlib import Path

from alarm_generator import AlarmDefinition, AlarmGeneratorOutbox

from . import config


class ModemAlarmSource:
    def __init__(self) -> None:
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

    def observe(self, state: str, timestamp: str) -> None:
        if state not in {"abierto", "cerrado"}:
            return
        self.outbox.observe(
            "modem:link",
            state == "cerrado",
            timestamp,
            subject="Router telef. puerto de escucha cerrado",
            body=f"El puerto observado del router telefonico se encuentra {state}.",
        )
