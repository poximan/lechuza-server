# src/app.py
import threading
from pathlib import Path

from flask import Flask, jsonify, redirect, request, send_from_directory
from werkzeug.middleware.proxy_fix import ProxyFix

from src.servicios.mqtt.mqtt_client_manager import MqttClientManager

from src.servicios.mqtt import mqtt_event_bus
from src.servicios.mqtt.mqtt_rpc import MqttRequestRouter

from src.servicios.email.estado_email import start_email_health_monitor
from src.logger import Logosaurio
from src.web.react_api import ReactApi
import config


# instancia de logger de aplicacion
logger_app = Logosaurio()

api_key = config.MENSAGELO_API_KEY

APP_HOST = config.LECHU_HOST
APP_PORT = config.LECHU_PORT
DEBUG_MODE = False
USE_RELOADER = False
AUTO_START_MQTT = True
_services_lock = threading.Lock()
_services_started = False
FRONTEND_DIR = Path(__file__).resolve().parents[1] / "frontend"
server = Flask(__name__, static_folder=None)
server.wsgi_app = ProxyFix(server.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)


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


@server.get("/lechu")
def frontend_redirect():
    return redirect("/lechu/", code=308)


@server.get("/lechu/")
@server.get("/lechu/<path:frontend_path>")
def frontend(frontend_path: str = ""):
    if frontend_path.startswith("api/"):
        return jsonify({"error": "api_route_not_found"}), 404
    candidate = FRONTEND_DIR / frontend_path
    if frontend_path and candidate.is_file():
        return send_from_directory(FRONTEND_DIR, frontend_path)
    return send_from_directory(FRONTEND_DIR, "index.html")


def _start_background_services():
    """
    Inicializa servicios permanentes (MQTT, RPC y monitor email) una sola vez.
    """
    global _services_started
    if _services_started:
        return
    with _services_lock:
        if _services_started:
            return

        logger_app.log("Inicializando servicios de lechu...", origin="APP")

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
