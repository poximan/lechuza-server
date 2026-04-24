import os
from datetime import datetime, timezone
from typing import Optional, Union
from zoneinfo import ZoneInfo


class TimeAuthority:
    """
    API centralizada para emitir y validar fechas en UTC con precision a segundos.
    """

    def __init__(self, tz_name: Optional[str] = None) -> None:
        raw_tz = self._require_tz_name(tz_name)
        self._tz_name = raw_tz
        self._local_tz = self._resolve_timezone(raw_tz)

    @staticmethod
    def _require_tz_name(tz_name: Optional[str]) -> str:
        if tz_name and tz_name.strip():
            return tz_name.strip()
        env_tz = os.getenv("TZ")
        if env_tz and env_tz.strip():
            return env_tz.strip()
        raise EnvironmentError("Falta variable de entorno obligatoria: TZ")

    @staticmethod
    def _resolve_timezone(name: str) -> timezone:
        try:
            return ZoneInfo(name)
        except Exception as exc:
            raise ValueError(f"Zona horaria invalida: {name}") from exc

    @property
    def timezone_name(self) -> str:
        return self._tz_name

    def refresh_timezone(self) -> None:
        """
        Relee la variable TZ (permite cambios dinamicos en contenedores).
        """
        raw_tz = self._require_tz_name(None)
        self._tz_name = raw_tz
        self._local_tz = self._resolve_timezone(raw_tz)

    def utc_now(self) -> datetime:
        """
        Retorna datetime timezone-aware en UTC truncado a segundos.
        """
        return datetime.now(timezone.utc).replace(microsecond=0)

    def utc_iso(self, value: Optional[datetime] = None) -> str:
        """
        Serializa en ISO-8601 con sufijo Z (UTC) y segundos como maxima precision.
        """
        dt = self.ensure_utc(value or self.utc_now())
        text = dt.isoformat()
        return text.replace("+00:00", "Z")

    def ensure_utc(self, value: datetime) -> datetime:
        """
        Normaliza cualquier datetime timezone-aware a UTC y remueve microsegundos.
        """
        if value.tzinfo is None:
            raise ValueError("datetime sin zona horaria")
        return value.astimezone(timezone.utc).replace(microsecond=0)

    def parse(
        self,
        value: Union[str, datetime],
        *,
        assume_utc_on_naive: bool = False,
    ) -> datetime:
        """
        Convierte string ISO o datetime timezone-aware a UTC.
        Si assume_utc_on_naive es True y la entrada no tiene zona, se asume UTC.
        """
        if isinstance(value, datetime):
            dt = value
        elif isinstance(value, str):
            text = value.strip()
            if not text:
                raise ValueError("timestamp vacio")
            if text.endswith("Z"):
                text = text[:-1] + "+00:00"
            dt = datetime.fromisoformat(text)
        else:
            raise TypeError("tipo no soportado para parsear timestamp")

        if dt.tzinfo is None:
            if not assume_utc_on_naive:
                raise ValueError("timestamp sin informacion de zona horaria")
            dt = dt.replace(tzinfo=timezone.utc)

        return self.ensure_utc(dt)

    def to_local(self, value: Union[str, datetime], *, assume_utc_on_naive: bool = False) -> datetime:
        """
        Convierte el timestamp recibido a la zona local configurada.
        """
        utc_dt = self.parse(value, assume_utc_on_naive=assume_utc_on_naive)
        return utc_dt.astimezone(self._local_tz)

    def format_local(
        self,
        value: Union[str, datetime],
        fmt: str = "%Y-%m-%d %H:%M:%S",
        *,
        assume_utc_on_naive: bool = False,
    ) -> str:
        """
        Convierte a zona local y serializa usando el formato solicitado.
        """
        local_dt = self.to_local(value, assume_utc_on_naive=assume_utc_on_naive)
        return local_dt.strftime(fmt)


_DEFAULT_AUTHORITY = TimeAuthority()


def get_time_authority() -> TimeAuthority:
    return _DEFAULT_AUTHORITY
