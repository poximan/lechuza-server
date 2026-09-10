import math
import statistics
from typing import Any
from .alarm_time import _minutes_between

def summarize_dashboard(count_rows, condition_row, frequency_rows, lifetime_rows):
    metrics: dict[tuple[str, str], dict[str, Any]] = {}
    for row in lifetime_rows:
        source_id = str(row["source_id"])
        alarm_key = str(row["alarm_key"])
        key = (source_id, alarm_key)
        entry = metrics.setdefault(
            key,
            {
                "source_id": source_id,
                "alarm_key": alarm_key,
                "title": str(row["title"]),
                "category": str(row["category"]),
                "configured_minutes": int(row["expected_clearance_minutes"]),
                "active_samples": [],
                "inactive_samples": [],
                "last_resolved_at": None,
            },
        )
        if row["qualified_at"] is None:
            continue
        last_resolved_at = entry["last_resolved_at"]
        if last_resolved_at is not None:
            entry["inactive_samples"].append(
                _minutes_between(str(last_resolved_at), str(row["qualified_at"]))
            )
        if row["resolved_at"] is not None:
            entry["active_samples"].append(
                _minutes_between(str(row["qualified_at"]), str(row["resolved_at"]))
            )
            entry["last_resolved_at"] = str(row["resolved_at"])
    lifetimes = []
    for entry in metrics.values():
        active_samples = sorted(entry.pop("active_samples"))
        inactive_samples = sorted(entry.pop("inactive_samples"))
        entry.pop("last_resolved_at")
        entry.update(_sample_metrics(active_samples, "active"))
        entry.update(_sample_metrics(inactive_samples, "inactive"))
        lifetimes.append(entry)
    lifetimes.sort(
        key=lambda item: (
            -item["active_sample_count"],
            item["source_id"],
            item["alarm_key"],
        )
    )
    counts = {str(row["status"]): int(row["total"]) for row in count_rows}
    return {
        "counts": {
            "potential": counts.get("potential", 0),
            "active": counts.get("active", 0),
            "recovering": counts.get("recovering", 0),
            "resolved": counts.get("resolved", 0),
        },
        "conditions": {
            "active": int(condition_row["active"] or 0),
            "inactive": int(condition_row["inactive"] or 0),
            "unknown": int(condition_row["unknown"] or 0),
        },
        "frequent": [dict(row) for row in frequency_rows],
        "clearance": lifetimes,
    }


def _sample_metrics(samples: list[float], prefix: str) -> dict[str, Any]:
    return {
        f"{prefix}_sample_count": len(samples),
        f"median_{prefix}_minutes": (
            round(statistics.median(samples), 1) if samples else None
        ),
        f"p90_{prefix}_minutes": (
            round(samples[max(0, math.ceil(len(samples) * 0.9) - 1)], 1)
            if samples
            else None
        ),
    }


