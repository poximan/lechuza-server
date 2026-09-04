from __future__ import annotations

import hmac
import json
import os
import re
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query, status


_IDENTIFIER_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._:-]{0,127}$")


@dataclass(frozen=True)
class AlarmDefinition:
    alarm_key: str
    title: str
    category: str
    expected_clearance_minutes: int

    def validate(self) -> None:
        if not _IDENTIFIER_PATTERN.fullmatch(self.alarm_key):
            raise ValueError(f"Clave de alarma invalida: {self.alarm_key!r}")
        if not self.title.strip() or not self.category.strip():
            raise ValueError(f"Catalogo incompleto para {self.alarm_key}")
        if self.expected_clearance_minutes < 0:
            raise ValueError(f"Tiempo de despeje invalido para {self.alarm_key}")


class AlarmGeneratorOutbox:
    """Conserva catalogo, estado observado y flancos pendientes de entrega."""

    SCHEMA_VERSION = 1

    def __init__(
        self,
        source_id: str,
        state_file: Path,
        *,
        activation_seconds: int,
        recovery_seconds: int,
    ) -> None:
        if not _IDENTIFIER_PATTERN.fullmatch(source_id):
            raise ValueError(f"Identificador de fuente invalido: {source_id!r}")
        if activation_seconds < 0 or recovery_seconds < 0:
            raise ValueError(f"Temporizacion invalida para {source_id}")
        self.source_id = source_id
        self.state_file = state_file
        self.activation_seconds = activation_seconds
        self.recovery_seconds = recovery_seconds
        self._lock = threading.RLock()
        self._catalog: dict[str, AlarmDefinition] = {}
        self._state = self._load()

    def register(self, definition: AlarmDefinition) -> None:
        definition.validate()
        with self._lock:
            self._catalog[definition.alarm_key] = definition

    def observe(
        self,
        alarm_key: str,
        condition_active: bool,
        occurred_at: str,
        *,
        subject: str,
        body: str,
    ) -> bool:
        if not isinstance(condition_active, bool):
            raise TypeError("condition_active debe ser booleano")
        self._validate_instant(occurred_at)
        if not subject.strip() or not body.strip():
            raise ValueError("El asunto y el cuerpo de alarma son obligatorios")
        with self._lock:
            if alarm_key not in self._catalog:
                raise KeyError(f"Alarma no registrada en catalogo: {alarm_key}")
            conditions = self._state["conditions"]
            previous = conditions.get(alarm_key)
            current = {
                "active": bool(condition_active),
                "condition_since_at": occurred_at,
                "subject": subject,
                "body": body,
            }
            if previous is not None and bool(previous["active"]) == bool(condition_active):
                if previous.get("subject") != subject or previous.get("body") != body:
                    previous["subject"] = subject
                    previous["body"] = body
                    self._save()
                return False

            conditions[alarm_key] = current
            if previous is not None or condition_active:
                event_id = int(self._state["next_event_id"])
                self._state["next_event_id"] = event_id + 1
                self._state["events"].append(
                    {
                        "event_id": event_id,
                        "alarm_key": alarm_key,
                        "condition_active": bool(condition_active),
                        "occurred_at": occurred_at,
                        "subject": subject,
                        "body": body,
                    }
                )
            self._save()
            return True

    def catalog_snapshot(self) -> dict[str, Any]:
        with self._lock:
            conditions = self._state["conditions"]
            alarms = []
            for alarm_key in sorted(self._catalog):
                definition = asdict(self._catalog[alarm_key])
                definition["activation_seconds"] = self.activation_seconds
                definition["recovery_seconds"] = self.recovery_seconds
                observed = conditions.get(alarm_key)
                definition["condition_active"] = (
                    bool(observed["active"]) if observed is not None else None
                )
                definition["condition_since_at"] = (
                    str(observed["condition_since_at"])
                    if observed is not None
                    else None
                )
                definition["subject"] = (
                    str(observed["subject"]) if observed is not None else definition["title"]
                )
                definition["body"] = (
                    str(observed["body"]) if observed is not None else ""
                )
                alarms.append(definition)
            return {"source_id": self.source_id, "alarms": alarms}

    def events_snapshot(self, after_event_id: int, limit: int) -> dict[str, Any]:
        safe_limit = min(1000, max(1, int(limit)))
        with self._lock:
            available = [
                dict(event)
                for event in self._state["events"]
                if int(event["event_id"]) > after_event_id
            ]
            selected = available[:safe_limit]
            return {
                "source_id": self.source_id,
                "events": selected,
                "last_event_id": (
                    int(selected[-1]["event_id"]) if selected else after_event_id
                ),
                "has_more": len(available) > len(selected),
            }

    def acknowledge(self, through_event_id: int) -> None:
        if through_event_id < 0:
            raise ValueError("El cursor confirmado no puede ser negativo")
        with self._lock:
            last_acked = int(self._state["last_acked_event_id"])
            if through_event_id <= last_acked:
                return
            last_emitted = int(self._state["next_event_id"]) - 1
            if through_event_id > last_emitted:
                raise ValueError(
                    f"El cursor {through_event_id} supera el ultimo evento {last_emitted}"
                )
            self._state["events"] = [
                event
                for event in self._state["events"]
                if int(event["event_id"]) > through_event_id
            ]
            self._state["last_acked_event_id"] = through_event_id
            self._save()

    def _load(self) -> dict[str, Any]:
        if not self.state_file.exists():
            return {
                "schema_version": self.SCHEMA_VERSION,
                "source_id": self.source_id,
                "next_event_id": 1,
                "last_acked_event_id": 0,
                "conditions": {},
                "events": [],
            }
        try:
            loaded = json.loads(self.state_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(
                f"No se pudo leer el estado del generador: {self.state_file}"
            ) from exc
        if not isinstance(loaded, dict) or loaded.get("schema_version") != self.SCHEMA_VERSION:
            raise RuntimeError(
                f"Contrato de estado invalido en {self.state_file}"
            )
        if loaded.get("source_id") != self.source_id:
            raise RuntimeError(
                f"Identidad de fuente invalida en {self.state_file}"
            )
        next_event_id = loaded.get("next_event_id")
        last_acked_event_id = loaded.get("last_acked_event_id")
        conditions = loaded.get("conditions")
        events = loaded.get("events")
        if (
            not isinstance(next_event_id, int)
            or isinstance(next_event_id, bool)
            or next_event_id < 1
            or not isinstance(last_acked_event_id, int)
            or isinstance(last_acked_event_id, bool)
            or last_acked_event_id < 0
            or last_acked_event_id >= next_event_id
            or not isinstance(conditions, dict)
            or not isinstance(events, list)
        ):
            raise RuntimeError(f"Contenido de estado invalido en {self.state_file}")
        expected_event_id = last_acked_event_id + 1
        for alarm_key, condition in conditions.items():
            if not isinstance(alarm_key, str) or not isinstance(condition, dict):
                raise RuntimeError(f"Condicion invalida en {self.state_file}")
            if not isinstance(condition.get("active"), bool):
                raise RuntimeError(f"Estado de condicion invalido en {self.state_file}")
            self._validate_instant(str(condition.get("condition_since_at") or ""))
            if not isinstance(condition.get("subject"), str) or not isinstance(
                condition.get("body"), str
            ):
                raise RuntimeError(f"Contenido de condicion invalido en {self.state_file}")
        for event in events:
            if not isinstance(event, dict) or event.get("event_id") != expected_event_id:
                raise RuntimeError(f"Secuencia de eventos invalida en {self.state_file}")
            if not isinstance(event.get("condition_active"), bool):
                raise RuntimeError(f"Flanco invalido en {self.state_file}")
            self._validate_instant(str(event.get("occurred_at") or ""))
            expected_event_id += 1
        if expected_event_id != next_event_id:
            raise RuntimeError(f"Cursor de eventos invalido en {self.state_file}")
        return loaded

    @staticmethod
    def _validate_instant(value: str) -> None:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError(f"Timestamp UTC invalido: {value!r}") from exc
        if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
            raise ValueError(f"Timestamp sin zona UTC: {value!r}")

    def _save(self) -> None:
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.state_file.with_suffix(f"{self.state_file.suffix}.tmp")
        payload = json.dumps(
            self._state,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        temporary.write_text(payload, encoding="utf-8")
        os.replace(temporary, self.state_file)


def create_alarm_generator_router(
    outbox: AlarmGeneratorOutbox,
    api_key: str,
    *,
    base_path: str = "",
) -> APIRouter:
    if not api_key:
        raise ValueError("La clave interna de alarmas es obligatoria")
    normalized_base = base_path.rstrip("/")
    if normalized_base and not normalized_base.startswith("/"):
        raise ValueError("base_path debe comenzar con '/'")
    router = APIRouter(prefix=f"{normalized_base}/api/v1/alarms")

    def authorize(value: str | None) -> None:
        if value is None or not hmac.compare_digest(value, api_key):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="unauthorized",
            )

    @router.get("/catalog")
    def catalog(
        x_api_key: str | None = Header(None, alias="X-API-Key"),
    ) -> dict[str, Any]:
        authorize(x_api_key)
        return outbox.catalog_snapshot()

    @router.get("/events")
    def events(
        after_event_id: int = Query(0, ge=0),
        limit: int = Query(500, ge=1, le=1000),
        x_api_key: str | None = Header(None, alias="X-API-Key"),
    ) -> dict[str, Any]:
        authorize(x_api_key)
        return outbox.events_snapshot(after_event_id, limit)

    @router.post("/events/ack")
    def acknowledge(
        payload: dict[str, Any],
        x_api_key: str | None = Header(None, alias="X-API-Key"),
    ) -> dict[str, Any]:
        authorize(x_api_key)
        value = payload.get("through_event_id")
        if not isinstance(value, int):
            raise HTTPException(status_code=422, detail="through_event_id invalido")
        try:
            outbox.acknowledge(value)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {"ok": True, "through_event_id": value}

    return router
