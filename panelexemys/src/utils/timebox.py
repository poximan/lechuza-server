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


def utc_iso(dt: datetime | None = None) -> str:
    return _AUTH.utc_iso(dt)


def parse(value: TimestampLike, *, legacy: bool = False) -> datetime:
    return _AUTH.parse(value, assume_utc_on_naive=legacy)


def to_local(value: TimestampLike, *, legacy: bool = False) -> datetime:
    return _AUTH.to_local(value, assume_utc_on_naive=legacy)


def format_local(value: TimestampLike, fmt: str = "%Y-%m-%d %H:%M:%S", *, legacy: bool = False) -> str:
    return _AUTH.format_local(value, fmt, assume_utc_on_naive=legacy)
