import os


def _req(name: str) -> str:
    v = os.getenv(name)
    if v is None or not v.strip():
        raise EnvironmentError(f"Falta variable de entorno obligatoria: {name}")
    return v.strip()


def _req_int(name: str) -> int:
    return int(_req(name))


def _req_float(name: str) -> float:
    return float(_req(name))


def _req_bool(name: str) -> bool:
    return _req(name).lower() in {"1", "true", "yes", "on"}


def _parse_csv_ints(raw: str) -> list[int]:
    return [int(x.strip()) for x in raw.split(",") if x.strip()]


def _req_csv(name: str) -> list[str]:
    raw = _req(name)
    items = [x.strip() for x in raw.split(",") if x.strip()]
    if not items:
        raise EnvironmentError(f"Falta variable de entorno obligatoria: {name}")
    return items


# ---------------------------------------------------------
# --- Panelexemys (host/puerto) ---------------------------
# ---------------------------------------------------------
PANELEXEMYS_HOST = _req("PANELEXEMYS_HOST")
PANELEXEMYS_PORT = _req_int("PANELEXEMYS_PORT")
PANELEXEMYS_DATA_DIR = _req("PANELEXEMYS_DATA_DIR")

# ---------------------------------------------------------
# --- Cliente HTTP hacia modbus-mw-service ----------------
# ---------------------------------------------------------
MODBUS_MW_API_BASE = _req("MODBUS_MW_API_BASE")
MODBUS_MW_HTTP_TIMEOUT = _req_int("MODBUS_MW_HTTP_TIMEOUT")
MODBUS_HTTP_POLL_SECONDS = _req_int("MODBUS_HTTP_POLL_SECONDS")

# ---------------------------------------------------------
# --- Dashboard (dash_config) -----------------------------
# ---------------------------------------------------------
PUBLIC_BASE_URL = _req("PUBLIC_BASE_URL").rstrip("/")
DASH_REFRESH_SECONDS = _req_int("DASH_REFRESH_SECONDS")      # Intervalo unico (ms) para todos los dcc.Interval
GLOBAL_THRESHOLD_ROJO = _req_int("GLOBAL_THRESHOLD_ROJO")    # Porcentaje debajo del cual conectividad "roja" (0-39)
GLOBAL_THRESHOLD_AMARILLO = _req_int("GLOBAL_THRESHOLD_AMARILLO")  # Porcentaje debajo del cual conectividad "amarilla" (40-89)

# ---------------------------------------------------------
# --- Notificador de Alarmas ------------------------------
# ---------------------------------------------------------
ALARM_CHECK_INTERVAL_SECONDS = _req_int("ALARM_CHECK_INTERVAL_SECONDS")  # Intervalo para revisar condicion de alarma
ALARM_MIN_SUSTAINED_DURATION_MINUTES = _req_int("ALARM_MIN_SUSTAINED_DURATION_MINUTES")  # Cuanto debe sostenerse una alarma para enviar email
ALARM_EMAIL_RECIPIENT = _req_csv("ALARM_EMAIL_RECIPIENT")
ALARM_EMAIL_SUBJECT_PREFIX = _req("ALARM_EMAIL_SUBJECT_PREFIX")  # Prefijo para el asunto del email

# ---------------------------------------------------------
# --- Mensagelo (servicio HTTP de mensajeria) -------------
# ---------------------------------------------------------
# Parametros de conexion al microservicio mensagelo (reemplaza SMTP local)
MENSAGELO_BASE_URL = _req("MENSAGELO_BASE_URL")
MENSAGELO_TIMEOUT_SECONDS = _req_int("MENSAGELO_TIMEOUT_SECONDS")
MENSAGELO_API_KEY = _req("MENSAGELO_API_KEY")

# Politica de reintentos con backoff para el enqueue HTTP (send_async)
MENSAGELO_MAX_RETRIES = _req_int("MENSAGELO_MAX_RETRIES")
MENSAGELO_BACKOFF_INITIAL = _req_float("MENSAGELO_BACKOFF_INITIAL")   # segundos
MENSAGELO_BACKOFF_MAX = _req_float("MENSAGELO_BACKOFF_MAX")           # segundos

# ---------------------------------------------------------
# --- MQTT ------------------------------------------------
# ---------------------------------------------------------

MQTT_BROKER_HOST = _req("MQTT_BROKER_HOST")
MQTT_BROKER_PORT = _req_int("MQTT_BROKER_PORT")
MQTT_BROKER_USERNAME = _req("MQTT_BROKER_USERNAME")
MQTT_BROKER_PASSWORD = _req("MQTT_BROKER_PASSWORD")

MQTT_BROKER_KEEPALIVE = _req_int("MQTT_BROKER_KEEPALIVE")   # heartbeat con el broker
MQTT_CONNECT_TIMEOUT = _req_int("MQTT_CONNECT_TIMEOUT")      # cuanto esperar la primera confirmacion de conexion

# Reconexion
MQTT_RECONNECT_DELAY_MIN = int(_req("MQTT_RECONNECT_DELAY_MIN"))
MQTT_RECONNECT_DELAY_MAX = int(_req("MQTT_RECONNECT_DELAY_MAX"))

# TLS
MQTT_BROKER_USE_TLS = _req_bool("MQTT_BROKER_USE_TLS")
MQTT_BROKER_CA_CERT = os.getenv("MQTT_BROKER_CA_CERT")
MQTT_CLIENT_CERTFILE = os.getenv("MQTT_CLIENT_CERTFILE")
MQTT_CLIENT_KEYFILE = os.getenv("MQTT_CLIENT_KEYFILE")
MQTT_TLS_INSECURE = _req_bool("MQTT_TLS_INSECURE")

# Presencia del sistema (queda igual, no afecta al movil)
MQTT_SERVICE_STATUS_TOPIC = _req("MQTT_SERVICE_STATUS_TOPIC")
MQTT_SERVICE_STATUS_QOS = _req_int("MQTT_SERVICE_STATUS_QOS")
MQTT_SERVICE_STATUS_RETAIN = _req_bool("MQTT_SERVICE_STATUS_RETAIN")

MQTT_WILL_TOPIC = MQTT_SERVICE_STATUS_TOPIC
MQTT_WILL_PAYLOAD = _req("MQTT_WILL_PAYLOAD")
MQTT_WILL_QOS = MQTT_SERVICE_STATUS_QOS
MQTT_WILL_RETAIN = MQTT_SERVICE_STATUS_RETAIN

MQTT_ONLINE_TOPIC = MQTT_SERVICE_STATUS_TOPIC
MQTT_ONLINE_QOS = MQTT_SERVICE_STATUS_QOS
MQTT_ONLINE_RETAIN = MQTT_SERVICE_STATUS_RETAIN

# -------- LOS 3 TOPICOS EXACTOS QUE USA EL MOVIL ----------
# (coinciden con tu MqttConfig en Android)
MQTT_TOPIC_MODEM_CONEXION = _req("MQTT_TOPIC_MODEM_CONEXION")  # payload: {"estado":"abierto"|"cerrado"|"desconocido","ts":"..."}
MQTT_TOPIC_GRADO = _req("MQTT_TOPIC_GRADO")                    # payload: {"porcentaje": 58.3, "total": N, "conectados": M, "ts": "..."}
MQTT_TOPIC_GRDS = _req("MQTT_TOPIC_GRDS")                      # payload: {"items":[{"id":11,"nombre":"...","ultima_caida":"..."}], "ts":"..."}
MQTT_TOPIC_EMAIL_ESTADO = _req("MQTT_TOPIC_EMAIL_ESTADO")      # payload: {"smtp":"conectado","ping_local":"desconectado","ping_remoto":"conectado","ts":"..."}
MQTT_TOPIC_EMAIL_EVENT = _req("MQTT_TOPIC_EMAIL_EVENT")        # payload: {"type":"email","subject":"...","ok":true,"ts":"..."}
MQTT_TOPIC_PROXMOX_ESTADO = _req("MQTT_TOPIC_PROXMOX_ESTADO")  # payload: {"ts":"...","status":"online|offline","vms":[...],"missing":[...]}
# QoS/retain por defecto
MQTT_PUBLISH_QOS_STATE = _req_int("MQTT_PUBLISH_QOS_STATE")
MQTT_PUBLISH_RETAIN_STATE = _req_bool("MQTT_PUBLISH_RETAIN_STATE")
MQTT_PUBLISH_QOS_EVENT = _req_int("MQTT_PUBLISH_QOS_EVENT")
MQTT_PUBLISH_RETAIN_EVENT = _req_bool("MQTT_PUBLISH_RETAIN_EVENT")

ROUTER_SERVICE_BASE_URL = _req("ROUTER_SERVICE_BASE_URL").rstrip("/")
ROUTER_CLIENT_TIMEOUT_SECONDS = _req_int("ROUTER_CLIENT_TIMEOUT_SECONDS")
MODEM_EXTERNAL_CHECK_URL = _req("MODEM_EXTERNAL_CHECK_URL")
MODEM_ADMIN_URL = _req("MODEM_ADMIN_URL")

# ---------------------------------------------------------
# --- charito (frontend + alarmas) ------------------------
# ---------------------------------------------------------
CHARITO_API_BASE = _req("CHARITO_API_BASE")
CHARITO_STALE_THRESHOLD_SECONDS = _req_int("CHARITO_STALE_THRESHOLD_SECONDS")

# ---------------------------------------------------------
# --- salud de correo -------------------------------------
# ---------------------------------------------------------
EMAIL_HEALTH_SMTP_HOST = _req("EMAIL_HEALTH_SMTP_HOST")
EMAIL_HEALTH_PING_LOCAL_HOST = _req("EMAIL_HEALTH_PING_LOCAL_HOST")
EMAIL_HEALTH_PING_REMOTE_HOST = _req("EMAIL_HEALTH_PING_REMOTE_HOST")

# ---------------- RPC sobre MQTT (request/response) ----------------------
# El cliente publica requests en este arbol. El servidor responde SIEMPRE
# usando alguno de los topicos ya suscritos por el movil (reply_to).
MQTT_RPC_REQ_ROOT = "app/req"        # nos suscribimos a "app/req/#"
# Acciones soportadas (para validacion/evolucion)
MQTT_RPC_ALLOWED_ACTIONS = {
    "get_global_status",   # responde en estado/exemys con resumen + ultimos estados por GRD
    "get_modem_status",    # responde en estado/sensor con estado del modem
    "send_email_test",     # dispara un correo de prueba via mensagelo
}

# TOPICOS VALIDOS PARA reply_to
MQTT_RPC_ALLOWED_REPLY_TO = {
    MQTT_TOPIC_MODEM_CONEXION,
    MQTT_TOPIC_GRADO,
    MQTT_TOPIC_GRDS,
    MQTT_TOPIC_EMAIL_EVENT,
}

# ---------------------------------------------------------
# --- Proxmox (PVE) ---------------------------------------
# ---------------------------------------------------------
PVE_API_BASE = _req("PVE_API_BASE")
PVE_NODE_NAME = _req("PVE_NODE_NAME")
PVE_VHOST_IDS = _parse_csv_ints(_req("PVE_VHOST_IDS"))
PVE_POLL_INTERVAL_SECONDS = _req_int("PVE_POLL_INTERVAL_SECONDS")
PVE_HTTP_TIMEOUT_SECONDS = _req_int("PVE_HTTP_TIMEOUT_SECONDS")
PVE_VERIFY_SSL = _req("PVE_VERIFY_SSL").lower() in {"1", "true", "yes", "on"}
PVE_HISTORY_HOURS = _req_int("PVE_HISTORY_HOURS")
PVE_MQTT_PUBLISH_FACTOR = _req_int("PVE_MQTT_PUBLISH_FACTOR")
