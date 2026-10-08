import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    locations: tuple[dict, ...]
    resolution: str = "PT15M"
    retention_months: int = 2
    daily_time: str = "00:10"
    retry_hours: tuple[int, ...] = (1, 2)
    http_timeout_seconds: int = 30
    page_size: int = 5000

    @classmethod
    def load(cls, path: str) -> "Settings":
        data = json.loads(Path(path).read_text())
        settings = cls(**{**data, "locations": tuple(data["locations"]),
                          "retry_hours": tuple(data.get("retry_hours", [1, 2]))})
        if not settings.locations or len({x["id"] for x in settings.locations}) != len(settings.locations):
            raise ValueError("Debe configurar ubicaciones únicas")
        if any(not x.get("id") or not x.get("name") for x in settings.locations):
            raise ValueError("Cada ubicación requiere id y name")
        if settings.resolution not in {"RAW", "PT15M"}:
            raise ValueError("Resolución no soportada")
        hour, minute = map(int, settings.daily_time.split(":"))
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError("Horario inválido")
        if not (1 <= settings.retention_months <= 12 and 1 <= settings.page_size <= 5000
                and 1 <= settings.http_timeout_seconds <= 120
                and all(isinstance(x, int) and 1 <= x <= 24 for x in settings.retry_hours)):
            raise ValueError("Configuración fuera de rango")
        return settings


def credentials(path: str) -> tuple[str, str]:
    values = {}
    for line in Path(path).read_text().splitlines():
        if line.strip() and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    if not values.get("client_id") or not values.get("client_secret"):
        raise ValueError("Faltan credenciales Sentryx")
    return values["client_id"], values["client_secret"]
