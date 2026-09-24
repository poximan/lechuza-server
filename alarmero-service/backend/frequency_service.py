from __future__ import annotations

from bisect import bisect_left, insort
from collections import defaultdict
from datetime import date, datetime, timedelta
import threading
from typing import Any

from timeauthority import get_time_authority

from .alarm_time import _parse_instant
from .frequency_repository import load_frequency_history


_WINDOWS = (("daily", 1), ("weekly", 7), ("monthly", 30), ("annual", 365))
_TIME = get_time_authority()


class FrequencyService:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._loaded_day: date | None = None
        self._catalog: dict[tuple[str, str], dict[str, str]] = {}
        self._first_observed: dict[tuple[str, str], datetime] = {}
        self._incidents: dict[str, tuple[tuple[str, str], datetime]] = {}
        self._starts: dict[tuple[str, str], list[datetime]] = {}

    def refresh_if_new_day(self) -> None:
        now = _TIME.utc_now()
        local_day = _TIME.to_local(now).date()
        with self._lock:
            if self._loaded_day == local_day:
                return
            catalog_rows, incident_rows = load_frequency_history()
            catalog = {
                (str(row["source_id"]), str(row["alarm_key"])): {
                    "source_id": str(row["source_id"]),
                    "alarm_key": str(row["alarm_key"]),
                    "title": str(row["title"]),
                    "category": str(row["category"]),
                }
                for row in catalog_rows
                if int(row["catalog_active"]) == 1
            }
            observed = {
                (str(row["source_id"]), str(row["alarm_key"])): _parse_instant(
                    str(row["first_observed_at"])
                )
                for row in catalog_rows
                if row["first_observed_at"] is not None
            }
            for key, instant in self._first_observed.items():
                if key not in observed or instant < observed[key]:
                    observed[key] = instant
            incidents = {
                str(row["incident_id"]): (
                    (str(row["source_id"]), str(row["alarm_key"])),
                    _parse_instant(str(row["first_seen_at"])),
                )
                for row in incident_rows
            }
            for incident_id, record in self._incidents.items():
                if incident_id not in incidents:
                    incidents[incident_id] = record
            starts: dict[tuple[str, str], list[datetime]] = defaultdict(list)
            for key, instant in incidents.values():
                starts[key].append(instant)
            for values in starts.values():
                values.sort()
            self._catalog = catalog
            self._first_observed = observed
            self._incidents = incidents
            self._starts = dict(starts)
            self._loaded_day = local_day

    def update_catalog(self, source_id: str, alarms: list[dict[str, Any]]) -> None:
        with self._lock:
            current = {(source_id, str(item["alarm_key"])) for item in alarms}
            for key in list(self._catalog):
                if key[0] == source_id and key not in current:
                    self._catalog.pop(key)
            for item in alarms:
                key = (source_id, str(item["alarm_key"]))
                self._catalog[key] = {
                    "source_id": source_id,
                    "alarm_key": key[1],
                    "title": str(item["title"]),
                    "category": str(item["category"]),
                }
                if key not in self._starts:
                    self._starts[key] = sorted(
                        instant for incident_key, instant in self._incidents.values()
                        if incident_key == key
                    )
                since = item.get("condition_since_at")
                if since is not None:
                    self._observe(key, str(since))

    def retain_sources(self, source_ids: set[str]) -> None:
        with self._lock:
            for key in list(self._catalog):
                if key[0] not in source_ids:
                    self._catalog.pop(key)

    def record_observations(self, observations: list[dict[str, str]]) -> None:
        with self._lock:
            for item in observations:
                self._observe(
                    (item["source_id"], item["alarm_key"]), item["occurred_at"]
                )

    def _observe(self, key: tuple[str, str], occurred_at: str) -> None:
        if key not in self._catalog:
            return
        instant = _parse_instant(occurred_at)
        previous = self._first_observed.get(key)
        if previous is None or instant < previous:
            self._first_observed[key] = instant

    def record_qualifications(self, qualifications: list[dict[str, str]]) -> None:
        with self._lock:
            for item in qualifications:
                incident_id = item["incident_id"]
                if incident_id in self._incidents:
                    continue
                key = (item["source_id"], item["alarm_key"])
                instant = _parse_instant(item["first_seen_at"])
                self._incidents[incident_id] = (key, instant)
                insort(self._starts.setdefault(key, []), instant)

    def snapshot(self, now: datetime) -> list[dict[str, Any]]:
        boundaries = {name: now - timedelta(days=days) for name, days in _WINDOWS}
        with self._lock:
            if self._loaded_day is None:
                raise RuntimeError("La frecuencia historica no fue inicializada")
            result = []
            for key, metadata in self._catalog.items():
                starts = self._starts.get(key, [])
                first_observed = self._first_observed.get(key)
                row: dict[str, Any] = {**metadata, "total": len(starts)}
                for name, boundary in boundaries.items():
                    row[name] = (
                        len(starts) - bisect_left(starts, boundary)
                        if first_observed is not None and first_observed <= boundary
                        else None
                    )
                result.append(row)
            result.sort(key=lambda row: (-row["total"], row["source_id"], row["alarm_key"]))
            return result
