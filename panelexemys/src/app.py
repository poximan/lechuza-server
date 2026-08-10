# src/app.py
import hmac
import os
import threading
import time
from pathlib import Path

from flask import Flask, jsonify, redirect, request, send_from_directory
from werkzeug.middleware.proxy_fix import ProxyFix

from src.servicios.mqtt.mqtt_client_manager import MqttClientManager

from src.servicios.mqtt import mqtt_event_bus
from src.servicios.mqtt.mqtt_rpc import MqttRequestRouter

from src.servicios.email.estado_email import start_email_health_monitor
from src.alarmas.notif_manager import NotifManager
from src.logger import Logosaurio
from src.dao.dao_alarm_incidents import alarm_incidents_dao
from src.web.react_api import ReactApi
import config


# instancia de logger de aplicacion
logger_app = Logosaurio()

api_key = config.MENSAGELO_API_KEY

APP_HOST = config.PANELEXEMYS_HOST
APP_PORT = config.PANELEXEMYS_PORT
DEBUG_MODE = False
USE_RELOADER = False
AUTO_START_MQTT = True
_services_lock = threading.Lock()
_services_started = False
FRONTEND_DIR = Path(__file__).resolve().parents[1] / "frontend"
server = Flask(__name__, static_folder=None)
server.wsgi_app = ProxyFix(server.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)


@server.get("/internal/alarms")
def alarm_lifecycle_snapshot():
    """Expone el ciclo de vida; panelexemys conserva su propiedad y su SQLite."""
    supplied_key = request.headers.get("X-API-Key", "")
    if not hmac.compare_digest(supplied_key, config.MENSAGELO_API_KEY):
        return jsonify({"error": "unauthorized"}), 401
    try:
        after_event_id = int(request.args.get("after_event_id", "0"))
        event_limit = int(request.args.get("event_limit", "1000"))
    except ValueError:
        return jsonify({"error": "invalid_pagination"}), 400
    return jsonify(alarm_incidents_dao.snapshot(after_event_id, event_limit))


@server.before_request
def log_user_ip():
    """
    registra ip origen y ruta http para trazabilidad
    """
    ip_addr = request.remote_addr
    if ip_addr != "127.0.0.1":
        logger_app.log(
            f"Solicitud HTTP de la IP: {ip_addr} para la ruta: {request.path}",
            origin="APP/HTTP",
        )

mqtt_client_manager = MqttClientManager(logger_app)

# exponer manager al event bus de publicaciones
mqtt_event_bus.set_manager(mqtt_client_manager)

# router rpc mqtt (suscribe y procesa requests en la cola)
rpc_router = MqttRequestRouter(logger_app, mqtt_client_manager, api_key)
server.register_blueprint(ReactApi(mqtt_client_manager).blueprint)


@server.get("/panelexemys")
def frontend_redirect():
    return redirect("/panelexemys/", code=308)


@server.get("/panelexemys/")
@server.get("/panelexemys/<path:frontend_path>")
def frontend(frontend_path: str = ""):
    if frontend_path.startswith("api/"):
        return jsonify({"error": "api_route_not_found"}), 404
    candidate = FRONTEND_DIR / frontend_path
    if frontend_path and candidate.is_file():
        return send_from_directory(FRONTEND_DIR, frontend_path)
    return send_from_directory(FRONTEND_DIR, "index.html")


def _load_grd_exclusion_ids(logger: Logosaurio) -> set:
    """
    Lee la lista de GRD a excluir de alarmas individuales.
    """
    exclusion_path = os.path.join(os.path.dirname(__file__), "alarmas", "grd_exclusion_list.txt")
    excluded: set[int] = set()
    try:
        with open(exclusion_path, "r", encoding="utf-8") as fh:
            for raw_line in fh:
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue
                try:
                    excluded.add(int(line))
                except ValueError:
                    logger.log(f"Entrada invalida en grd_exclusion_list: '{line}'", origin="ALRM/INIT")
    except FileNotFoundError:
        logger.log("No se encontro grd_exclusion_list.txt. No habra exclusiones.", origin="ALRM/INIT")
    except Exception as exc:
        logger.log(f"ERROR leyendo grd_exclusion_list.txt: {exc}", origin="ALRM/INIT")
    else:
        if excluded:
            logger.log(f"GRD excluidos de alarmas: {sorted(excluded)}", origin="ALRM/INIT")
    return excluded


def _start_alarm_manager(logger: Logosaurio) -> None:
    """
    Inicializa NotifManager en un hilo en segundo plano.
    """
    excluded_ids = _load_grd_exclusion_ids(logger)
    interval = max(1, int(config.ALARM_CHECK_INTERVAL_SECONDS))
    manager = NotifManager(logger, excluded_ids, api_key)

    def alarm_loop() -> None:
        while True:
            try:
                manager.run_alarm_processing()
            except Exception as exc:
                logger.log(f"ERROR en ciclo de NotifManager: {exc}", origin="ALRM/LOOP")
            time.sleep(interval)

    threading.Thread(target=alarm_loop, name="notif-manager", daemon=True).start()


def _start_background_services():
    """
    Inicializa servicios permanentes (MQTT, RPC, monitor email y alarmas) una sola vez.
    """
    global _services_started
    if _services_started:
        return
    with _services_lock:
        if _services_started:
            return

        logger_app.log("Inicializando servicios de panelexemys...", origin="APP")

        if AUTO_START_MQTT:
            logger_app.log("Lanzando cliente MQTT...", origin="APP")
            threading.Thread(target=mqtt_client_manager.start, daemon=True).start()
        else:
            logger_app.log("Cliente MQTT configurado para no auto iniciar.", origin="APP")

        logger_app.log("Iniciando RPC sobre MQTT...", origin="APP")
        threading.Thread(target=rpc_router.start, daemon=True).start()

        logger_app.log("Lanzando monitor servidor email (SMTP NOOP)...", origin="APP")
        threading.Thread(
            target=start_email_health_monitor,
            args=(logger_app, mqtt_client_manager),
            daemon=True,
        ).start()

        logger_app.log("Lanzando gestor de alarmas...", origin="APP")
        _start_alarm_manager(logger_app)

        _services_started = True


_start_background_services()


if __name__ == "__main__":
    logger_app.log("Iniciando servidor React/Flask...", origin="APP")
    server.run(
        debug=DEBUG_MODE,
        use_reloader=USE_RELOADER,
        host=APP_HOST,
        port=APP_PORT,
    )
