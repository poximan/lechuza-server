from pathlib import Path
from typing import Any

from alarm_generator import AlarmDefinition, AlarmGeneratorOutbox
from src import config
from src.utils import timebox


class GrdAlarmGenerator:
    def __init__(self) -> None:
        self.exemys_outbox = AlarmGeneratorOutbox(
            "modbus-exemys", Path(config.ALARM_OUTBOX_FILE), activation_seconds=1200, recovery_seconds=20
        )
        self.exemys_outbox.register(AlarmDefinition(
            alarm_key="exemys:global-red", title="Conectividad global Exemys en zona roja",
            category="exemys_global", expected_clearance_minutes=120,
        ))

    def observe_grd_snapshot(self, contract: dict[str, Any], descriptions: dict[int, str]) -> None:
        summary = contract.get("summary")
        disconnected = contract.get("disconnected")
        unavailable = contract.get("unavailable")
        if not isinstance(summary, dict) or not isinstance(disconnected, list) or not isinstance(unavailable, list):
            raise ValueError("Snapshot GRD invalido para alarmas")
        if any(isinstance(item, dict) and item.get("disconnect_confirmed") is not True for item in unavailable):
            return
        percentage = float(summary["porcentaje"])
        now = timebox.utc_iso()
        global_red = percentage < config.GLOBAL_RED_THRESHOLD
        self.exemys_outbox.observe(
            "exemys:global-red", global_red, now, subject="Middleware sin conexion",
            body=f"La conectividad global Exemys permanece en zona roja ({percentage:.2f}%).",
        )
        disconnected_ids = {int(item["id_grd"]) for item in disconnected if isinstance(item, dict) and "id_grd" in item}
        for grd_id, description in descriptions.items():
            key = f"exemys:grd:{grd_id}"
            self.exemys_outbox.register(AlarmDefinition(
                alarm_key=key, title=f"{description} sin conexion", category="exemys_grd",
                expected_clearance_minutes=120,
            ))
            active = not global_red and grd_id in disconnected_ids
            self.exemys_outbox.observe(key, active, now, subject=f"{description} sin conexion", body=f"GRD {description} sin conexion; conectividad global {percentage:.2f}%.")
