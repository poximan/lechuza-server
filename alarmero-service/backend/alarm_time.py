from datetime import datetime, timedelta, timezone

def _parse_instant(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise ValueError(f"Timestamp fuera de UTC: {value}")
    return parsed.astimezone(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def _minutes_between(start: str, end: str) -> float:
    return max(0.0, (_parse_instant(end) - _parse_instant(start)).total_seconds() / 60.0)


