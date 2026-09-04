from __future__ import annotations

from pathlib import Path
from typing import Any

from alarm_generator import AlarmDefinition, AlarmGeneratorOutbox

from . import config
from .utils import timebox


class PveAlarmSource:
    def __init__(self) -> None:
        self.outbox = AlarmGeneratorOutbox(
            "pve-service",
            Path(config.DATA_DIR) / "alarm-events.json",
            activation_seconds=1200,
            recovery_seconds=20,
        )
        self.outbox.register(
            AlarmDefinition(
                alarm_key="proxmox:host",
                title="Hipervisor Proxmox no responde",
                category="proxmox_host",
                expected_clearance_minutes=120,
            )
        )
        for vmid in config.PVE_VHOST_IDS:
            self._register_vm(vmid, f"VM {vmid}")

    def observe(self, snapshot: dict[str, Any]) -> None:
        timestamp = str(snapshot.get("ts") or timebox.utc_iso())
        error = str(snapshot.get("error") or "").strip()
        host_active = bool(error) or str(snapshot.get("status")) != "online"
        self.outbox.observe(
            "proxmox:host",
            host_active,
            timestamp,
            subject="Hipervisor Proxmox no responde",
            body=(
                "El hipervisor Proxmox no responde."
                + (f" Detalle: {error}" if error else "")
            ),
        )
        if host_active:
            return

        vm_by_id = {
            int(item["vmid"]): item
            for item in snapshot.get("vms", [])
            if isinstance(item, dict) and "vmid" in item
        }
        for vmid in config.PVE_VHOST_IDS:
            item = vm_by_id.get(vmid)
            name = str(item.get("name") or f"VM {vmid}") if item else f"VM {vmid}"
            self._register_vm(vmid, name)
            vm_status = str(item.get("status") or "sin datos") if item else "sin datos"
            active = vm_status.lower() != "running"
            self.outbox.observe(
                f"proxmox:vm:{vmid}",
                active,
                timestamp,
                subject=f"{name} detenida en Proxmox",
                body=f"{name} (ID {vmid}) presenta estado '{vm_status}'.",
            )

    def _register_vm(self, vmid: int, name: str) -> None:
        self.outbox.register(
            AlarmDefinition(
                alarm_key=f"proxmox:vm:{vmid}",
                title=f"{name} detenida en Proxmox",
                category="proxmox_vm",
                expected_clearance_minutes=60,
            )
        )
