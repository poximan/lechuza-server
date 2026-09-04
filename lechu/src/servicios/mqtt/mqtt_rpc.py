"""

RPC sobre MQTT.

- El cliente publica en el arbol configurado `MQTT_RPC_REQ_ROOT`.
- El servidor responde solo en `MQTT_RPC_RES_ROOT/{clientId}/{corr}`.

"""

import json
import uuid
from typing import Optional, Tuple
from src.control.bounded_work_queue import BoundedWorkQueue
from src.logger import Logosaurio
from src.utils import timebox
from src.servicios.email.mensagelo_client import MensageloClient
from src.servicios.mqtt import mqtt_event_bus
from src.web.clients.modbus_client import modbus_client
from src.web.clients.modem_link_monitor_client import modem_link_monitor_client
import config


REQ_PREFIX = config.MQTT_RPC_REQ_ROOT



class MqttRequestRouter:

    """

    enrutador simple de requests rpc sobre mqtt basado en topicos

    """

    def __init__(self, logger: Logosaurio, mqtt_manager, key):

        self.log = logger

        self.manager = mqtt_manager

        self._listener_queue = BoundedWorkQueue[Tuple[str, str]](
            config.MQTT_RPC_QUEUE_MAXSIZE
        )

        self._listener = None

        self._origen = "OBS/RPC"

        self._mail_client = MensageloClient(

            base_url=config.MENSAGELO_BASE_URL,

            api_key=key,

            timeout_seconds=int(config.MENSAGELO_TIMEOUT_SECONDS),

            max_retries=int(config.MENSAGELO_MAX_RETRIES),

            backoff_initial=float(config.MENSAGELO_BACKOFF_INITIAL),

            backoff_max=float(config.MENSAGELO_BACKOFF_MAX)

            )



    def start(self):

        """

        inicia suscripcion a requests y procesa mensajes entrantes

        """

        self.manager.subscribe(f"{REQ_PREFIX}/#", qos=1, source=self._origen)

        if self._listener is None:

            def _enqueue(topic: str, payload: str) -> None:
                if not self._listener_queue.try_put((topic, payload)):
                    stats = self._listener_queue.snapshot()
                    self.log.log(
                        f"RPC MQTT rechazado por cola completa: {stats}",
                        origin=self._origen,
                    )

            self._listener = _enqueue

            self.manager.register_prefix_listener(f"{REQ_PREFIX}/", self._listener, source=self._origen)

        self.log.log(f"RPC MQTT: suscripto a {REQ_PREFIX}/#", origin=self._origen)



        while True:

            topic, payload = self._listener_queue.get()
            self._listener_queue.task_done()



            action = topic[len(REQ_PREFIX) + 1:]



            try:

                req = json.loads(payload)

            except Exception:

                self.log.log("RPC descartado: payload JSON invalido", origin=self._origen)

                continue



            reply_to = str(req.get("reply_to") or "").strip()

            corr = str(req.get("corr") or "").strip()

            params = req.get("params", {})



            if not self._valid_reply_to(reply_to, corr):

                self.log.log(f"RPC descartado: reply_to invalido para accion {action}", origin=self._origen)

                continue



            if action not in config.MQTT_RPC_ALLOWED_ACTIONS:

                self._emit_error(corr, reply_to, action, f"accion no soportada: {action}")

                continue



            if action == "get_global_status":

                self._handle_get_global_status(corr, reply_to)

            elif action == "get_modem_status":

                self._handle_get_modem_status(corr, reply_to)

            elif action == "get_ge_status":

                self._handle_get_ge_status(corr, reply_to)

            elif action == "send_email_test":

                self._handle_send_email_test(corr, reply_to, params)

            else:

                self._emit_error(corr, reply_to, action, "accion no implementada")



    # ----------------- handlers -----------------



    def _valid_reply_to(self, reply_to: str, corr: str) -> bool:

        if not corr:

            return False

        prefix = f"{config.MQTT_RPC_RES_ROOT}/"

        if not reply_to.startswith(prefix):

            return False

        parts = reply_to[len(prefix):].split("/")

        return len(parts) == 2 and bool(parts[0]) and parts[1] == corr



    def _handle_get_global_status(self, corr: str, reply_to: str):

        """

        arma resumen global de conectividad y estados actuales por grd

        """

        try:
            summary_payload = modbus_client.get_summary()
        except Exception as exc:
            self.log.log(
                f"RPC global status fallo: {exc}",
                origin=self._origen,
            )
            self._emit_error(
                corr,
                reply_to,
                "get_global_status",
                f"no se pudo consultar el estado global: {exc}",
            )
            return
        latest_states = summary_payload.get("states", {})
        summary = summary_payload.get("summary", {})
        data = {
            "ts": timebox.utc_iso(),
            "summary": summary,
            "states": latest_states
        }
        self._emit_ok(corr, reply_to, "get_global_status", data)


    def _handle_get_modem_status(self, corr: str, reply_to: str):
        """
        devuelve estado del modem consultando modem-link-monitor
        """
        try:
            status_data = modem_link_monitor_client.get_status()
            estado = str(status_data["state"])
        except Exception as exc:
            self.log.log(f"RPC modem status fallo: {exc}", origin=self._origen)
            self._emit_error(
                corr,
                reply_to,
                "get_modem_status",
                f"no se pudo consultar el estado del modem: {exc}",
            )
            return
        data = {"ts": timebox.utc_iso(), "estado": estado}
        self._emit_ok(corr, reply_to, "get_modem_status", data)


    def _handle_get_ge_status(self, corr: str, reply_to: str):
        """
        devuelve el estado vigente de interruptores GE desde modbus-collector-service
        """
        try:
            data = modbus_client.get_ge_status()
        except Exception as exc:
            self._emit_error(corr, reply_to, "get_ge_status", str(exc))
            return
        self._emit_ok(corr, reply_to, "get_ge_status", data)


    def _handle_send_email_test(self, corr: str, reply_to: str, params: dict):

        """

        Encola un correo de prueba usando Mensagelo y responde con el resultado.

        """

        origin_raw = ""

        if isinstance(params, dict):

            origin_raw = str(params.get("origin", "")).strip()

        origin_key = origin_raw.lower() or "lechu"

        origin_labels = {

            "panelito": "Panelito - app movil",

            "lechu": "Lechu - backend",

        }

        origin_label = origin_labels.get(origin_key, origin_raw or "Lechu - backend")



        subject = ""

        if isinstance(params, dict):

            subject = str(params.get("subject", "")).strip()

        if not subject:

            subject = f"Email de Prueba ({origin_label})"

        elif origin_label.lower() not in subject.lower():

            subject = f"{subject} [{origin_label}]"



        body = ""

        if isinstance(params, dict):

            body = str(params.get("body", "")).strip()

        marker = "origen de la prueba"

        if not body:

            body = (
                f"Este es un email de prueba enviado desde {origin_label}. "
                f"Fecha y Hora: {timebox.format_local(timebox.utc_now())}"
            )
        elif marker not in body.lower():

            body = f"{body}\n\nOrigen de la prueba: {origin_label}"



        recipients = config.EMAIL_TEST_RECIPIENTS

        prefix = config.EMAIL_TEST_SUBJECT_PREFIX

        full_subject = f"{prefix}{subject}"



        try:

            ok, msg = self._mail_client.enqueue_email(

                recipients=recipients,

                subject=full_subject,

                body=body,

                message_type="maintenance_test",

                idempotency_key=str(

                    uuid.uuid5(uuid.NAMESPACE_URL, f"lechu:mqtt:{corr}")

                ),

            )

        except Exception as exc:

            ok = False

            msg = str(exc)



        try:

            mqtt_event_bus.publish_email_event(full_subject, ok)

        except Exception:

            pass



        if ok:

            self._emit_ok(

                corr,

                reply_to,

                "send_email_test",

                {"ok": True, "message": msg or "ok"},

            )

        else:

            self._emit_error(corr, reply_to, "send_email_test", msg or "error enviando email")



    # ----------------- emisores -----------------



    def _emit_ok(self, corr: Optional[str], reply_to: str, action: str, data: dict):

        """

        publica respuesta ok en el topico reply_to

        """

        msg = {"type": "rpc", "action": action, "corr": corr, "ok": True, "data": data}

        self.manager.publish(

            reply_to,

            json.dumps(msg, ensure_ascii=False),

            qos=config.MQTT_PUBLISH_QOS_STATE,

            retain=False,

            source=self._origen,

        )



    def _emit_error(self, corr: Optional[str], reply_to: str, action: str, error: str):

        """

        publica respuesta de error en reply_to

        """

        msg = {"type": "rpc", "action": action, "corr": corr, "ok": False, "error": error}

        self.manager.publish(

            reply_to,

            json.dumps(msg, ensure_ascii=False),

            qos=config.MQTT_PUBLISH_QOS_STATE,

            retain=False,

            source=self._origen,

        )















