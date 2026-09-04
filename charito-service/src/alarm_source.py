from pathlib import Path

from alarm_generator import AlarmDefinition, AlarmGeneratorOutbox
from timeauthority import get_time_authority

from config import Target


_TIME = get_time_authority()


class CharitoAlarmSource:
    def __init__(self, data_dir: Path, targets: list[Target]) -> None:
        self.outbox = AlarmGeneratorOutbox(
            "charito-service",
            data_dir / "alarm-events.json",
            activation_seconds=1200,
            recovery_seconds=20,
        )
        for target in targets:
            self._register(target.instance_id, target.alias)

    def observe(self, snapshot: dict) -> None:
        timestamp = str(snapshot.get("ts") or _TIME.utc_iso())
        for item in snapshot.get("items", []):
            if not isinstance(item, dict):
                continue
            instance_id = str(item.get("instanceId") or "").strip()
            if not instance_id:
                continue
            alias = str(item.get("alias") or instance_id)
            status = str(item.get("status") or "desconocido").lower()
            if status == "desconocido":
                continue
            self._register(instance_id, alias)
            detail = str(item.get("dataError") or "").strip()
            self.outbox.observe(
                f"charito:{instance_id}",
                status != "online",
                timestamp,
                subject=f"charo-daemon {alias} fuera de servicio",
                body=(
                    f"charo-daemon {alias} (ID {instance_id}) presenta estado "
                    f"'{status}'." + (f" Detalle: {detail}" if detail else "")
                ),
            )

    def _register(self, instance_id: str, alias: str) -> None:
        self.outbox.register(
            AlarmDefinition(
                alarm_key=f"charito:{instance_id}",
                title=f"charo-daemon {alias} fuera de servicio",
                category="charito",
                expected_clearance_minutes=60,
            )
        )
