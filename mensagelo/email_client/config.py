import os


def _req(name: str) -> str:
    value = os.getenv(name)
    if value is None or not value.strip():
        raise EnvironmentError(f"Falta variable de entorno obligatoria: {name}")
    return value.strip()


# URL del servicio — un SOLO nombre, sin alias ni fallback
SERVICE_BASE_URL = _req("SERVICE_BASE_URL")

# Clave de API — un SOLO nombre
API_KEY = _req("API_KEY")
