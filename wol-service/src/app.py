import ipaddress
import json
import os
import re
import socket
import ssl
import threading
import time

import certifi
import paho.mqtt.client as mqtt
from timeauthority import get_time_authority


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
MAC_TEXT = required("WOL_TARGET_MAC")
if not re.fullmatch(r"(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}", MAC_TEXT):
    raise ValueError("WOL_TARGET_MAC invalida")
if SSH_TIMEOUT_SECONDS <= 0:
    raise ValueError("WOL_SSH_TIMEOUT_SECONDS debe ser positivo")
MAC_BYTES = bytes.fromhex(MAC_TEXT.replace(":", ""))
TIME = get_time_authority()


class WakeOnLanResponder:
    def __init__(self) -> None:
        self._busy_lock = threading.Lock()
        self._busy = False
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

        with self._busy_lock:
            if self._busy:
                self._publish_error(correlation, reply_to, "ya hay un encendido en seguimiento")
                return
            self._busy = True
        threading.Thread(
            target=self._wake_and_watch,
            args=(correlation, reply_to),
            name="wol-ssh-watch",
            daemon=True,
        ).start()

    def _wake_and_watch(self, correlation: str, reply_to: str) -> None:
        try:
            packet = b"\xff" * 6 + MAC_BYTES * 16
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp_socket:
                udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                sent = udp_socket.sendto(packet, (BROADCAST_IP, 9))
            if sent != len(packet):
                raise OSError(f"envio UDP incompleto: {sent}/{len(packet)} bytes")
            self._publish_ok(correlation, reply_to, "packet_sent")

            deadline = time.monotonic() + SSH_TIMEOUT_SECONDS
            while time.monotonic() < deadline:
                try:
                    with socket.create_connection((TARGET_IP, 22), timeout=1.0):
                        self._publish_ok(correlation, reply_to, "ssh_open", port=22)
                        return
                except OSError:
                    time.sleep(2.0)
            self._publish_error(
                correlation,
                reply_to,
                f"el puerto 22 de {TARGET_IP} no abrio dentro del plazo",
            )
        except Exception as exc:
            self._publish_error(correlation, reply_to, f"no se pudo emitir WoL: {exc}")
        finally:
            with self._busy_lock:
                self._busy = False

    def _valid_reply_to(self, reply_to: str, correlation: str) -> bool:
        prefix = f"{RESPONSE_ROOT}/"
        if not correlation or not reply_to.startswith(prefix):
            return False
        parts = reply_to[len(prefix):].split("/")
        return len(parts) == 2 and bool(parts[0]) and parts[1] == correlation

    def _publish_ok(self, correlation: str, reply_to: str, status: str, **extra) -> None:
        data = {
            "contract_version": 1,
            "status": status,
            "target_ip": TARGET_IP,
            "ts": TIME.utc_iso(),
            **extra,
        }
        self._publish(
            reply_to,
            {"type": "rpc", "action": "wake_host", "corr": correlation, "ok": True, "data": data},
        )

    def _publish_error(self, correlation: str, reply_to: str, error: str) -> None:
        self._publish(
            reply_to,
            {"type": "rpc", "action": "wake_host", "corr": correlation, "ok": False, "error": error},
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


if __name__ == "__main__":
    WakeOnLanResponder().run()
