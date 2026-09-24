import ipaddress
import json
import os
import re
import ssl
import time
from pathlib import Path

import certifi
import paho.mqtt.client as mqtt

from .control_api import ControlApi
from .wake_operation import WakeOperationBusy, WakeOperationManager


def required(name: str) -> str:
    value = os.getenv(name)
    if value is None or not value.strip():
        raise EnvironmentError(f"Falta variable de entorno obligatoria: {name}")
    return value.strip()


BROKER_HOST = required("MQTT_BROKER_HOST")
BROKER_PORT = int(required("MQTT_BROKER_PORT"))
BROKER_USERNAME = required("MQTT_BROKER_USERNAME")
BROKER_PASSWORD = required("MQTT_BROKER_PASSWORD")
BROKER_KEEPALIVE = int(required("MQTT_BROKER_KEEPALIVE"))
RECONNECT_MIN = int(required("MQTT_RECONNECT_DELAY_MIN"))
RECONNECT_MAX = int(required("MQTT_RECONNECT_DELAY_MAX"))
USE_TLS = required("MQTT_BROKER_USE_TLS").lower() in {"1", "true", "yes", "on"}
TLS_INSECURE = required("MQTT_TLS_INSECURE").lower() in {"1", "true", "yes", "on"}
REQUEST_TOPIC = required("MQTT_WOL_REQUEST_TOPIC")
RESPONSE_ROOT = required("MQTT_RPC_RES_ROOT").rstrip("/")
QOS = int(required("MQTT_PUBLISH_QOS_STATE"))
TARGET_IP = str(ipaddress.ip_address(required("WOL_TARGET_IP")))
BROADCAST_IP = str(ipaddress.ip_address(required("WOL_BROADCAST_IP")))
SSH_TIMEOUT_SECONDS = int(required("WOL_SSH_TIMEOUT_SECONDS"))
CONTROL_SOCKET = Path(required("WOL_CONTROL_SOCKET"))
MAC_TEXT = required("WOL_TARGET_MAC")
if not re.fullmatch(r"(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}", MAC_TEXT):
    raise ValueError("WOL_TARGET_MAC invalida")
if SSH_TIMEOUT_SECONDS <= 0:
    raise ValueError("WOL_SSH_TIMEOUT_SECONDS debe ser positivo")
MAC_BYTES = bytes.fromhex(MAC_TEXT.replace(":", ""))


class WakeOnLanResponder:
    def __init__(self, manager: WakeOperationManager) -> None:
        self.manager = manager
        self.client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id="lechu-wol-service",
        )
        self.client.username_pw_set(BROKER_USERNAME, BROKER_PASSWORD)
        self.client.reconnect_delay_set(min_delay=RECONNECT_MIN, max_delay=RECONNECT_MAX)
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        if USE_TLS:
            context = ssl.create_default_context(cafile=certifi.where())
            context.minimum_version = ssl.TLSVersion.TLSv1_2
            if TLS_INSECURE:
                context.check_hostname = False
                context.verify_mode = ssl.CERT_NONE
            self.client.tls_set_context(context)

    def run(self) -> None:
        while True:
            try:
                self.client.connect(BROKER_HOST, BROKER_PORT, keepalive=BROKER_KEEPALIVE)
                self.client.loop_forever()
            except Exception as exc:
                print(f"wol-service: conexion MQTT interrumpida: {exc}", flush=True)
                time.sleep(RECONNECT_MIN)

    def _on_connect(self, client, _userdata, _flags, reason_code, _properties=None) -> None:
        if reason_code == mqtt.CONNACK_ACCEPTED:
            client.subscribe(REQUEST_TOPIC, qos=QOS)
            print(f"wol-service: escuchando {REQUEST_TOPIC}", flush=True)
        else:
            print(f"wol-service: MQTT rechazo conexion rc={reason_code}", flush=True)

    def _on_message(self, _client, _userdata, message) -> None:
        try:
            request = json.loads(message.payload.decode("utf-8"))
            if not isinstance(request, dict):
                raise ValueError("la solicitud no es un objeto")
            correlation = str(request.get("corr") or "").strip()
            reply_to = str(request.get("reply_to") or "").strip()
            params = request.get("params")
            if not self._valid_reply_to(reply_to, correlation):
                print("wol-service: solicitud descartada por reply_to invalido", flush=True)
                return
            if not isinstance(params, dict) or params.get("contract_version") != 1:
                self._publish_error(correlation, reply_to, "contrato de solicitud invalido")
                return
        except Exception:
            print("wol-service: solicitud JSON invalida", flush=True)
            return

        try:
            self.manager.trigger(
                correlation,
                "panelito-mqtt",
                observer=lambda operation: self._publish_operation(reply_to, operation),
            )
        except WakeOperationBusy as exc:
            self._publish_error(
                correlation,
                reply_to,
                "ya hay un encendido en seguimiento",
                operation=exc.operation,
            )
        except ValueError as exc:
            self._publish_error(correlation, reply_to, str(exc))

    def _valid_reply_to(self, reply_to: str, correlation: str) -> bool:
        prefix = f"{RESPONSE_ROOT}/"
        if not correlation or not reply_to.startswith(prefix):
            return False
        parts = reply_to[len(prefix):].split("/")
        return len(parts) == 2 and bool(parts[0]) and parts[1] == correlation

    def _publish_operation(self, reply_to: str, operation: dict) -> None:
        correlation = str(operation["request_id"])
        if operation["status"] == "failed":
            self._publish_error(
                correlation,
                reply_to,
                str(operation.get("error") or "fallo WoL sin detalle"),
                operation=operation,
            )
            return
        self._publish(
            reply_to,
            {
                "type": "rpc",
                "action": "wake_host",
                "corr": correlation,
                "ok": True,
                "data": operation,
            },
        )

    def _publish_error(
        self,
        correlation: str,
        reply_to: str,
        error: str,
        **extra,
    ) -> None:
        self._publish(
            reply_to,
            {
                "type": "rpc",
                "action": "wake_host",
                "corr": correlation,
                "ok": False,
                "error": error,
                **extra,
            },
        )

    def _publish(self, topic: str, payload: dict) -> None:
        result = self.client.publish(
            topic,
            json.dumps(payload, ensure_ascii=False),
            qos=QOS,
            retain=False,
        )
        if result.rc != mqtt.MQTT_ERR_SUCCESS:
            raise RuntimeError(f"publicacion MQTT fallo rc={result.rc}")


def main() -> None:
    manager = WakeOperationManager(
        target_ip=TARGET_IP,
        target_mac=MAC_BYTES,
        broadcast_ip=BROADCAST_IP,
        ssh_timeout_seconds=SSH_TIMEOUT_SECONDS,
    )
    control_api = ControlApi(CONTROL_SOCKET, manager)
    control_api.start()
    try:
        WakeOnLanResponder(manager).run()
    finally:
        control_api.stop()


if __name__ == "__main__":
    main()
