import os


def _req(name: str) -> str:
    value = os.getenv(name)
    if value is None or not value.strip():
        raise EnvironmentError(f"Falta variable de entorno obligatoria: {name}")
    return value.strip()


def _req_int(name: str) -> int:
    return int(_req(name))


def _req_bool(name: str) -> bool:
    return _req(name).lower() in {"1", "true", "yes", "on"}


# --- Servicio HTTP ---
SERVICE_HOST = _req("SERVICE_HOST")
SERVICE_PORT = _req_int("SERVICE_PORT")

# --- Seguridad ---
API_KEY = _req("API_KEY")  # UNA sola clave, sin alias

# --- SMTP ---
SMTP_SERVER = _req("SMTP_SERVER")
SMTP_PORT = _req_int("SMTP_PORT")
SMTP_USERNAME = _req("SMTP_USERNAME")
SMTP_PASSWORD = _req("SMTP_PASSWORD")
SMTP_USE_TLS = _req_bool("SMTP_USE_TLS")
SMTP_TIMEOUT_SECONDS = _req_int("SMTP_TIMEOUT_SECONDS")

# --- Base de datos ---
DATABASE_DIR = _req("DATABASE_DIR")
DATABASE_NAME = _req("DATABASE_NAME")
DATABASE_PATH = os.path.join(DATABASE_DIR, DATABASE_NAME)

# --- Worker/cola ---
QUEUE_MAXSIZE = _req_int("QUEUE_MAXSIZE")
