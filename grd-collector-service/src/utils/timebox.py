from __future__ import annotations

from datetime import datetime
from typing import Union

from timeauthority import TimeAuthority, get_time_authority

_AUTH = get_time_authority()

TimestampLike = Union[str, datetime]


def authority() -> TimeAuthority:
    return _AUTH


def utc_now() -> datetime:
    return _AUTH.utc_now()


def utc_iso(value: datetime | None = None) -> str:
    return _AUTH.utc_iso(value)


def utc_iso_milliseconds(value: datetime) -> str:
    return _AUTH.utc_iso_milliseconds(value)


def utc_today_iso() -> str:
    return _AUTH.utc_today().isoformat()


def monotonic() -> float:
    return _AUTH.monotonic()


def parse_format(value: str, pattern: str) -> datetime:
    return _AUTH.parse_format(value, pattern)


def format_utc(value: datetime, pattern: str) -> str:
    return _AUTH.format_utc(value, pattern)


def utc_series(values):
    return _AUTH.utc_series(values)


def parse(value: TimestampLike, *, legacy: bool = False) -> datetime:
    return _AUTH.parse(value, assume_utc_on_naive=legacy)


def parse_preserving_subseconds(
    value: TimestampLike,
    *,
    legacy: bool = False,
) -> datetime:
    return _AUTH.parse_preserving_subseconds(
        value,
        assume_utc_on_naive=legacy,
    )


def format_local(value: TimestampLike, fmt: str = "%Y-%m-%d %H:%M:%S", *, legacy: bool = False) -> str:
    return _AUTH.format_local(value, fmt, assume_utc_on_naive=legacy)
