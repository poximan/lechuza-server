from pathlib import Path
from typing import Any
from alarm_generator import AlarmDefinition, AlarmGeneratorOutbox
from src import config
from src.utils import timebox

class GeneratorAlarmGenerator:
    def __init__(self) -> None:
        self.generator_outbox = AlarmGeneratorOutbox("modbus-generators", Path(config.ALARM_OUTBOX_FILE), activation_seconds=60, recovery_seconds=20)
        self._register("edif-estivariz", "edif. Estivariz"); self._register("edif-fontana", "edif. Fontana")
    def _register(self, generator_id: str, label: str) -> None:
        self.generator_outbox.register(AlarmDefinition(alarm_key=f"generator:{generator_id}:running", title=f"{label} grupo electrogeno en marcha", category="generator", expected_clearance_minutes=60))
    def observe_generator(self, generator_id: str, payload: dict[str, Any]) -> None:
        breaker = payload.get("interruptor_grupo")
        if not isinstance(breaker, dict) or breaker.get("bit") not in {0,1}: raise ValueError(f"Estado de grupo invalido para {generator_id}")
        label = str(payload.get("edificio") or generator_id); self._register(generator_id, label)
        active = int(breaker["bit"]) == 1
        self.generator_outbox.observe(f"generator:{generator_id}:running", active, str(payload.get("ts") or timebox.utc_iso()), subject=f"{label} grupo electrogeno en marcha", body=f"El interruptor lado grupo electrogeno de {label} se encuentra {'cerrado' if active else 'abierto'}.")
