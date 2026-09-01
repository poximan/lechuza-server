from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import time
from typing import Callable, Optional, Union


TimestampLike = Union[str, datetime]
UTC = timezone.utc
PRESENTATION_TIMEZONE = timezone(timedelta(hours=-3), name="UTC-03:00")


class TimeAuthority:
    """Autoridad temporal del sistema para UTC y presentacion UTC-3."""

    def __init__(
        self,
        utc_now_source: Callable[[], datetime] | None = None,
        monotonic_source: Callable[[], float] | None = None,
    ) -> None:
        self._utc_now_source = utc_now_source or (lambda: datetime.now(UTC))
        self._monotonic_source = monotonic_source or time.monotonic

    def utc_now(self) -> datetime:
        value = self._utc_now_source()
        if value.tzinfo is None:
            raise ValueError("La fuente de hora debe devolver un datetime con zona")
        return value.astimezone(UTC).replace(microsecond=0)

    def utc_today(self) -> date:
        return self.utc_now().date()

    def monotonic(self) -> float:
        return self._monotonic_source()

    def utc_iso(self, value: Optional[datetime] = None) -> str:
        normalized = self.ensure_utc(value or self.utc_now())
        return normalized.isoformat().replace("+00:00", "Z")

    def utc_iso_milliseconds(self, value: datetime) -> str:
        if value.tzinfo is None:
            raise ValueError("datetime sin zona horaria")
        normalized = value.astimezone(UTC)
        return normalized.isoformat(timespec="milliseconds").replace("+00:00", "Z")

    def ensure_utc(self, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("datetime sin zona horaria")
        return value.astimezone(UTC).replace(microsecond=0)

    def parse(
        self,
        value: TimestampLike,
        *,
        assume_utc_on_naive: bool = False,
    ) -> datetime:
        parsed = self._parse_value(
            value,
            assume_utc_on_naive=assume_utc_on_naive,
        )
        return self.ensure_utc(parsed)

    def parse_preserving_subseconds(
        self,
        value: TimestampLike,
        *,
        assume_utc_on_naive: bool = False,
    ) -> datetime:
        parsed = self._parse_value(
            value,
            assume_utc_on_naive=assume_utc_on_naive,
        )
        return parsed.astimezone(UTC)

    @staticmethod
    def _parse_value(
        value: TimestampLike,
        *,
        assume_utc_on_naive: bool,
    ) -> datetime:
        if isinstance(value, datetime):
            parsed = value
        elif isinstance(value, str):
            text = value.strip()
            if not text:
                raise ValueError("timestamp vacio")
            normalized_text = text[:-1] + "+00:00" if text.endswith("Z") else text
            parsed = datetime.fromisoformat(normalized_text)
        else:
            raise TypeError("tipo no soportado para parsear timestamp")

        if parsed.tzinfo is None:
            if not assume_utc_on_naive:
                raise ValueError("timestamp sin informacion de zona horaria")
            parsed = parsed.replace(tzinfo=UTC)
        return parsed

    def parse_format(self, value: str, pattern: str) -> datetime:
        parsed = datetime.strptime(value, pattern).replace(tzinfo=UTC)
        return self.ensure_utc(parsed)

    def format_utc(self, value: datetime, pattern: str) -> str:
        return self.ensure_utc(value).strftime(pattern)

    def utc_series(self, values):
        """Normaliza una serie tabular a instantes UTC sin exigir pandas al importar."""
        import pandas as pd

        return pd.to_datetime(values, utc=True)

    def to_local(
        self,
        value: TimestampLike,
        *,
        assume_utc_on_naive: bool = False,
    ) -> datetime:
        return self.parse(
            value,
            assume_utc_on_naive=assume_utc_on_naive,
        ).astimezone(PRESENTATION_TIMEZONE)

    def format_local(
        self,
        value: TimestampLike,
        fmt: str = "%Y-%m-%d %H:%M:%S",
        *,
        assume_utc_on_naive: bool = False,
    ) -> str:
        return self.to_local(
            value,
            assume_utc_on_naive=assume_utc_on_naive,
        ).strftime(fmt)


_DEFAULT_AUTHORITY = TimeAuthority()


def get_time_authority() -> TimeAuthority:
    return _DEFAULT_AUTHORITY
