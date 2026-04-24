import time
import subprocess
import platform
from typing import Literal, Dict, Optional, Any

import requests

from src.utils.paths import update_observar_key
from src.logger import Logosaurio
from src.utils import timebox
from ..mqtt.mqtt_topic_publisher import MqttTopicPublisher
import config

Estado = Literal["conectado", "desconectado", "desconocido"]


def _mensagelo_smtp_check(logger: Logosaurio) -> Estado:
    """
    Consulta a mensagelo el endpoint /smtppostserv para validar el SMTP configurado
    sin hacer NOOP directo desde este proceso.

    Respuestas:
      - "conectado" si status=http200 y body.status=="ok"
      - "desconectado" si status no 200 o body.status!="ok"
      - "desconocido" si faltan parametros de config
    """
    base_url: Optional[str] = config.MENSAGELO_BASE_URL
    api_key: Optional[str] = config.MENSAGELO_API_KEY
    timeout: int = int(config.MENSAGELO_TIMEOUT_SECONDS)

    url = f"{base_url.rstrip('/')}/smtppostserv"
    headers = {"X-API-Key": api_key}

    try:
        resp = requests.get(url, headers=headers, timeout=timeout)
        if resp.status_code == 200:
            try:
                data = resp.json() or {}
            except Exception:
                data = {}
            return "conectado" if str(data.get("status", "")).lower() == "ok" else "desconectado"
        else:
            # servicio responde pero indica problema
            return "desconectado"
    except requests.Timeout:
        try:
            logger.log("mensagelo /smtppostserv timeout", origin="EMAIL/CHK")
        except Exception:
            pass
        return "desconectado"
    except Exception as e:
        try:
            logger.log(f"mensagelo /smtppostserv excepcion: {e}", origin="EMAIL/CHK")
        except Exception:
            pass
        return "desconocido"


def _ping_host(host: str, logger: Logosaurio) -> Estado:
    """
    Ejecuta un ping con un intento y timeout corto a nivel SO.
    Controla el tiempo total del subproceso para evitar bloqueos.
    """
    if not host:
        return "desconocido"

    system = platform.system().lower()
    if "windows" in system:
        cmd = ["ping", "-n", "1", "-w", "2000", host]
    else:
        cmd = ["ping", "-c", "1", "-W", "2", host]

    try:
        res = subprocess.run(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=5,
        )
        return "conectado" if res.returncode == 0 else "desconectado"
    except subprocess.TimeoutExpired:
        try:
            logger.log(f"Ping {host} timeout", origin="EMAIL/CHK")
        except Exception:
            pass
        return "desconectado"
    except Exception as e:
        try:
            logger.log(f"Ping {host} excepcion: {e}", origin="EMAIL/CHK")
        except Exception:
            pass
        return "desconocido"


def _build_status(logger: Logosaurio) -> Dict[str, Estado]:
    """
    Calcula los tres estados y retorna el diccionario a persistir.
    smtp: estado del SMTP verificado via mensagelo /smtppostserv
    ping_local: ping al host local configurado
    ping_remoto: ping al host remoto configurado
    """
    estado_smtp = _mensagelo_smtp_check(logger)
    estado_ping_local = _ping_host(config.EMAIL_HEALTH_PING_LOCAL_HOST, logger)
    estado_ping_remoto = _ping_host(config.EMAIL_HEALTH_PING_REMOTE_HOST, logger)

    return {
        "smtp": estado_smtp,
        "ping_local": estado_ping_local,
        "ping_remoto": estado_ping_remoto,
    }


def start_email_health_monitor(logger: Logosaurio, mqtt_manager) -> None:
    """
    Bucle de monitoreo cada 300 s. Actualiza observar.json -> server_email_estado
    con subclaves smtp, ping_local y ping_remoto.
    """
    publisher = MqttTopicPublisher(logger=logger, manager=mqtt_manager)
    last_payload: Optional[Dict[str, Any]] = None

    while True:
        try:
            estados = _build_status(logger)
            update_observar_key("server_email_estado", estados)
            enriched_payload = {
                **estados,
                "ts": timebox.utc_iso(),
            }
            if enriched_payload != last_payload:
                publisher.publish_json(
                    config.MQTT_TOPIC_EMAIL_ESTADO,
                    enriched_payload,
                    qos=config.MQTT_PUBLISH_QOS_STATE,
                    retain=config.MQTT_PUBLISH_RETAIN_STATE,
                )
                last_payload = enriched_payload
            try:
                logger.log(f"server_email_estado: {enriched_payload}", origin="EMAIL/CHK")
            except Exception:
                pass
        except Exception as e:
            try:
                logger.log(f"persistencia observar.json error: {e}", origin="EMAIL/CHK")
            except Exception:
                pass
        finally:
            time.sleep(300)
