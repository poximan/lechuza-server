from __future__ import annotations

from pathlib import Path
from typing import Any

from alarm_generator import AlarmDefinition, AlarmGeneratorOutbox

from src import config
from src.utils import timebox


class ModbusAlarmGenerator:
    """Traduce estados Modbus validos a condiciones de alarma de dominio."""

    def __init__(self) -> None:
        outbox_path = Path(config.ALARM_OUTBOX_FILE)
        self.exemys_outbox = AlarmGeneratorOutbox(
            "modbus-exemys",
            outbox_path.with_name("alarm-events-exemys.json"),
            activation_seconds=1200,
            recovery_seconds=20,
        )
        self.generator_outbox = AlarmGeneratorOutbox(
            "modbus-generators",
            outbox_path.with_name("alarm-events-generators.json"),
            activation_seconds=60,
            recovery_seconds=20,
        )
        self.exemys_outbox.register(
            AlarmDefinition(
                alarm_key="exemys:global-red",
                title="Conectividad global Exemys en zona roja",
                category="exemys_global",
                expected_clearance_minutes=120,
            )
        )
        self._register_generator("edif-estivariz", "edif. Estivariz")
        self._register_generator("edif-fontana", "edif. Fontana")

    def observe_grd_snapshot(
        self,
        contract: dict[str, Any],
        descriptions: dict[int, str],
    ) -> None:
        summary = contract.get("summary")
        disconnected = contract.get("disconnected")
        unavailable = contract.get("unavailable")
        if not isinstance(summary, dict) or not isinstance(disconnected, list):
            raise ValueError("Snapshot GRD invalido para el generador de alarmas")
        if not isinstance(unavailable, list):
            raise ValueError("Snapshot GRD sin estado de disponibilidad")
        pending = [
            item
            for item in unavailable
            if isinstance(item, dict) and item.get("disconnect_confirmed") is not True
        ]
        if pending:
            return
        percentage = summary.get("porcentaje")
        if not isinstance(percentage, (int, float)):
            raise ValueError("Snapshot GRD sin porcentaje de conectividad")

        now = timebox.utc_iso()
        global_red = float(percentage) < config.GLOBAL_RED_THRESHOLD
        self.exemys_outbox.observe(
            "exemys:global-red",
            global_red,
            now,
            subject="Middleware sin conexion",
            body=(
                "La conectividad global Exemys permanece en zona roja "
                f"({float(percentage):.2f}%, umbral {config.GLOBAL_RED_THRESHOLD:.2f}%)."
            ),
        )

        disconnected_by_id = {
            int(item["id_grd"]): item
            for item in disconnected
            if isinstance(item, dict) and "id_grd" in item
        }
        for grd_id, description in descriptions.items():
            alarm_key = f"exemys:grd:{grd_id}"
            self.exemys_outbox.register(
                AlarmDefinition(
                    alarm_key=alarm_key,
                    title=f"{description} sin conexion",
                    category="exemys_grd",
                    expected_clearance_minutes=120,
                )
            )
            individual_active = not global_red and grd_id in disconnected_by_id
            self.exemys_outbox.observe(
                alarm_key,
                individual_active,
                now,
                subject=f"{description} sin conexion",
                body=(
                    f"GRD {description} sin conexion con conectividad global "
                    f"en {float(percentage):.2f}%."
                ),
            )

    def observe_generator(self, generator_id: str, payload: dict[str, Any]) -> None:
        breaker = payload.get("interruptor_grupo")
        if not isinstance(breaker, dict) or breaker.get("bit") not in {0, 1}:
            raise ValueError(
                f"Estado de grupo invalido para {generator_id}"
            )
        label = str(payload.get("edificio") or generator_id)
        self._register_generator(generator_id, label)
        active = int(breaker["bit"]) == 1
        self.generator_outbox.observe(
            f"generator:{generator_id}:running",
            active,
            str(payload.get("ts") or timebox.utc_iso()),
            subject=f"{label} grupo electrogeno en marcha",
            body=(
                f"El interruptor lado grupo electrogeno de {label} "
                f"se encuentra {'cerrado' if active else 'abierto'}."
            ),
        )

    def _register_generator(self, generator_id: str, label: str) -> None:
        self.generator_outbox.register(
            AlarmDefinition(
                alarm_key=f"generator:{generator_id}:running",
                title=f"{label} grupo electrogeno en marcha",
                category="generator",
                expected_clearance_minutes=60,
            )
        )
