from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path

from alarm_generator import AlarmDefinition, AlarmGeneratorOutbox


class ProcessAlarmService:
    def __init__(self, data_dir: Path, outbox: AlarmGeneratorOutbox) -> None:
        self._catalog_file = data_dir / "process-alarm-catalog.json"
        self._outbox = outbox
        self._processes = self._load_catalog()
        for key, entry in self._processes.items():
            self._register_definition(key, entry)

    def observe(self, item: dict, timestamp: str) -> None:
        instance_id = str(item.get("instanceId") or "").strip()
        if not instance_id:
            return
        host_reachable = item.get("hostReachable")
        if host_reachable is False:
            for key, entry in self._processes.items():
                if entry["instance_id"] == instance_id:
                    self._observe_process(key, entry, False, timestamp)
            return
        if host_reachable is not True or item.get("status") != "online":
            return

        sample = item.get("latestSample")
        processes = sample.get("watchedProcesses") if isinstance(sample, dict) else None
        if not isinstance(processes, list):
            processes = item.get("watchedProcesses")
        if not isinstance(processes, list):
            return
        alias = str(item.get("alias") or instance_id)
        for process in processes:
            if not isinstance(process, dict):
                continue
            process_name = process.get("processName")
            if not isinstance(process_name, str) or not process_name.strip():
                process_name = process.get("name")
            running = process.get("running")
            if not isinstance(process_name, str) or not process_name.strip():
                continue
            entry = {
                "instance_id": instance_id,
                "alias": alias,
                "process_name": process_name.strip(),
            }
            key = self._alarm_key(instance_id, entry["process_name"])
            self._register_process(key, entry)
            if isinstance(running, bool):
                self._observe_process(key, entry, not running, timestamp)

    @staticmethod
    def _alarm_key(instance_id: str, process_name: str) -> str:
        digest = hashlib.sha256(
            f"{instance_id}\0{process_name}".encode("utf-8")
        ).hexdigest()
        return f"charito:process:{digest}"

    def _register_process(self, key: str, entry: dict[str, str]) -> None:
        previous = self._processes.get(key)
        if previous == entry:
            return
        if previous is not None and (
            previous["instance_id"] != entry["instance_id"]
            or previous["process_name"] != entry["process_name"]
        ):
            raise ValueError(f"Identidad de proceso duplicada: {key}")
        updated = dict(self._processes)
        updated[key] = entry
        self._save_catalog(updated)
        self._processes = updated
        self._register_definition(key, entry)

    def _register_definition(self, key: str, entry: dict[str, str]) -> None:
        self._outbox.register(AlarmDefinition(
            alarm_key=key,
            title=f"{entry['process_name']} detenido en {entry['alias']}",
            category="charito_process",
            expected_clearance_minutes=60,
            activation_seconds=600,
        ))

    def _observe_process(
        self, key: str, entry: dict[str, str], active: bool, timestamp: str
    ) -> None:
        self._outbox.observe(
            key,
            active,
            timestamp,
            subject=f"Proceso {entry['process_name']} detenido en {entry['alias']}",
            body=(
                f"El proceso {entry['process_name']} del charo-daemon "
                f"{entry['alias']} (ID {entry['instance_id']}) "
                f"{'esta detenido' if active else 'ya no requiere alarma individual'}."
            ),
        )

    def _load_catalog(self) -> dict[str, dict[str, str]]:
        if not self._catalog_file.exists():
            return {}
        loaded = json.loads(self._catalog_file.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict) or loaded.get("schema_version") != 1:
            raise ValueError(f"Catalogo de procesos invalido: {self._catalog_file}")
        processes = loaded.get("processes")
        if not isinstance(processes, dict):
            raise ValueError(f"Procesos invalidos: {self._catalog_file}")
        result: dict[str, dict[str, str]] = {}
        for key, entry in processes.items():
            if not isinstance(entry, dict) or any(
                not isinstance(entry.get(field), str) or not entry[field].strip()
                for field in ("instance_id", "alias", "process_name")
            ):
                raise ValueError(f"Proceso invalido en {self._catalog_file}: {key}")
            if key != self._alarm_key(entry["instance_id"], entry["process_name"]):
                raise ValueError(f"Identidad invalida en {self._catalog_file}: {key}")
            result[key] = entry
        return result

    def _save_catalog(self, processes: dict[str, dict[str, str]]) -> None:
        self._catalog_file.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                "w", encoding="utf-8", dir=self._catalog_file.parent, delete=False
            ) as handle:
                temporary = handle.name
                json.dump(
                    {"schema_version": 1, "processes": processes},
                    handle, ensure_ascii=False, sort_keys=True,
                )
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self._catalog_file)
        finally:
            if temporary and os.path.exists(temporary):
                os.remove(temporary)
