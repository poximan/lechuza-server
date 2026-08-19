import uuid
from typing import List

from src.logger import Logosaurio
from ..servicios.mqtt import mqtt_event_bus as bus
from .categorias.notif_mw_global import NotifMwGlobal
from .categorias.notif_mw_nodo import NotifMwNodo
from .categorias.notif_modem import NotifModem
from .categorias.notif_ge_generadores import NotifGeGeneradores
from .categorias.notif_proxmox import NotifProxmoxHost, NotifProxmoxVm
from .categorias.notif_charito import NotifCharitoDaemon
from src.dao.dao_alarm_incidents import alarm_incidents_dao
from src.dao.dao_mensajes_enviados import mensajes_enviados_dao
from src.servicios.email.mensagelo_client import MensageloClient
from src.utils import timebox
from src.web.clients.modbus_client import modbus_client
from src.web.clients.proxmox_client import ProxmoxClient
from src.web.clients.charito_client import CharitoClient
import config


class NotifManager:
    """
    Orquestador de notificaciones:
    - Evalua condiciones y sus recuperaciones explicitas.
    - Conserva la identidad de cada incidencia en SQLite.
    - Encola email via mensagelo con clave idempotente.
    - Publica evento en MQTT y registra el intento local.
    """

    def __init__(self, logger: Logosaurio, excluded_grd_ids: set, key):
        self.logger = logger
        self.excluded_grd_ids = set(excluded_grd_ids)
        self.global_notifier = NotifMwGlobal(logger, self._observe_alarm_condition)
        self.nodo_notifier = NotifMwNodo(
            logger,
            excluded_grd_ids,
            self._observe_alarm_condition,
        )
        self.modem_notifier = NotifModem(logger, self._observe_alarm_condition)
        self.ge_notifier = NotifGeGeneradores(
            logger,
            buildings=[
                {
                    "key": "edif-estivariz",
                    "label": "edif. Estivariz",
                    "fetch_status": modbus_client.get_ge_edif_estivariz_status,
                    "sustained_closed_alarm": True,
                },
                {
                    "key": "edif-fontana",
                    "label": "edif. Fontana",
                    "fetch_status": modbus_client.get_ge_edif_fontana_status,
                },
            ],
            min_duration_seconds=60,
            on_condition=self._observe_alarm_condition,
        )
        self.proxmox_host_notifier = NotifProxmoxHost(
            logger,
            self._observe_alarm_condition,
        )
        self.proxmox_vm_notifier = NotifProxmoxVm(
            logger,
            self._observe_alarm_condition,
        )
        self.charito_notifier = NotifCharitoDaemon(
            logger,
            self._observe_alarm_condition,
        )
        self.proxmox_client = ProxmoxClient(config.PVE_API_BASE)
        self.charito_client = CharitoClient(config.CHARITO_API_BASE)
        self.mail_client = MensageloClient(
            base_url=config.MENSAGELO_BASE_URL,
            api_key=key,
            timeout_seconds=int(config.MENSAGELO_TIMEOUT_SECONDS),
            max_retries=int(config.MENSAGELO_MAX_RETRIES),
            backoff_initial=float(config.MENSAGELO_BACKOFF_INITIAL),
            backoff_max=float(config.MENSAGELO_BACKOFF_MAX),
        )

    def run_alarm_processing(self):
        try:
            summary = modbus_client.get_summary()
        except Exception as exc:
            self.logger.log(
                f"ERROR consultando resumen Modbus: {exc}. Se conservan las incidencias actuales.",
                origin="ALRM/MODBUS",
            )
        else:
            summary_data = summary.get("summary") if isinstance(summary, dict) else None
            disconnected = summary.get("disconnected") if isinstance(summary, dict) else None
            unavailable = summary.get("unavailable") if isinstance(summary, dict) else None
            percentage = summary_data.get("porcentaje") if isinstance(summary_data, dict) else None
            pending_reads = (
                [
                    item
                    for item in unavailable
                    if isinstance(item, dict) and item.get("disconnect_confirmed") is not True
                ]
                if isinstance(unavailable, list)
                else []
            )
            if pending_reads:
                self.logger.log(
                    f"Resumen Modbus con {len(pending_reads)} lecturas no disponibles sin confirmar. "
                    "Se conservan las incidencias actuales.",
                    origin="ALRM/MODBUS",
                )
            elif isinstance(percentage, (int, float)) and isinstance(disconnected, list):
                self._process_alarms(float(percentage), disconnected)
            else:
                self.logger.log(
                    "Resumen Modbus invalido. Se conservan las incidencias actuales.",
                    origin="ALRM/MODBUS",
                )

        self._process_proxmox_alarms(self._fetch_proxmox_snapshot())
        self._process_charito_alarms(self._fetch_charito_snapshot())

    def _fetch_proxmox_snapshot(self) -> dict:
        try:
            snapshot = self.proxmox_client.get_state()
            if isinstance(snapshot, dict):
                return snapshot
            self.logger.log("Snapshot Proxmox invalido (no dict).", origin="ALRM/PVE")
        except Exception as exc:
            self.logger.log(f"ERROR consultando estado Proxmox: {exc}", origin="ALRM/PVE")
        return {}

    def _fetch_charito_snapshot(self) -> dict:
        try:
            snapshot = self.charito_client.get_state()
            if isinstance(snapshot, dict):
                return snapshot
            self.logger.log("Snapshot charito invalido (no dict).", origin="ALRM/CHARITO")
        except Exception as exc:
            self.logger.log(f"ERROR consultando estado charito-service: {exc}", origin="ALRM/CHARITO")
        return {}

    def _process_alarms(self, current_percentage: float, disconnected_grds: list):
        disconnected_keys = {
            f"mw-node:{item['id_grd']}"
            for item in disconnected_grds
            if (
                isinstance(item, dict)
                and "id_grd" in item
                and item["id_grd"] not in self.excluded_grd_ids
            )
        }
        for active_key in alarm_incidents_dao.active_keys("mw-node:"):
            self._observe_alarm_condition(
                active_key,
                condition_active=active_key in disconnected_keys,
            )

        if self.global_notifier.evaluate_condition(current_percentage):
            subject = "Middleware sin conexion"
            body = (
                f"Conectividad global exemys ha caido por debajo del "
                f"{config.GLOBAL_THRESHOLD_ROJO}% ({current_percentage:.2f}%) por mas de "
                f"{config.ALARM_MIN_SUSTAINED_DURATION_MINUTES} minutos.\n"
            )
            self._send_notification_and_log(
                subject,
                body,
                config.ALARM_EMAIL_RECIPIENT,
                alarm_key="mw-global",
            )

        grds_to_alert = self.nodo_notifier.evaluate_condition(current_percentage, disconnected_grds)
        for grd_info in grds_to_alert:
            subject = f"{grd_info['description']} sin conexion"
            body = (
                f"GRD {grd_info['description']} sin conexion por mas de "
                f"{config.ALARM_MIN_SUSTAINED_DURATION_MINUTES} minutos, "
                f"con conectividad global por encima del "
                f"{config.GLOBAL_THRESHOLD_ROJO}% ({current_percentage:.2f}%).\n"
            )
            self._send_notification_and_log(
                subject,
                body,
                config.ALARM_EMAIL_RECIPIENT,
                alarm_key=f"mw-node:{grd_info['id_grd']}",
            )

        if self.modem_notifier.evaluate_condition():
            subject = "Router telef. puerto de escucha cerrado"
            body = (
                f"El modem conexion de exemys no puede ser alcanzado hace mas de "
                f"{config.ALARM_MIN_SUSTAINED_DURATION_MINUTES} minutos."
            )
            self._send_notification_and_log(
                subject,
                body,
                config.ALARM_EMAIL_RECIPIENT,
                alarm_key="modem-link",
            )

        for alert in self.ge_notifier.evaluate():
            self._send_notification_and_log(
                alert["subject"],
                alert["body"],
                config.ALARM_EMAIL_RECIPIENT,
                alarm_key=alert.get("alarm_key"),
            )

    def _process_proxmox_alarms(self, snapshot):
        if not isinstance(snapshot, dict):
            snapshot = {}

        if self.proxmox_host_notifier.evaluate_condition(snapshot):
            detail = self.proxmox_host_notifier.get_last_error() or ""
            body_lines = [
                f"El hipervisor Proxmox no responde desde hace al menos {config.ALARM_MIN_SUSTAINED_DURATION_MINUTES} minutos."
            ]
            if detail:
                body_lines.append(f"Detalle detectado: {detail}")
            self._send_notification_and_log(
                "Hipervisor Proxmox no responde",
                "\n".join(body_lines),
                config.ALARM_EMAIL_RECIPIENT,
                alarm_key="proxmox:host",
            )

        allow_vm_processing = self.proxmox_host_notifier.allow_vm_processing()
        vm_alerts = self.proxmox_vm_notifier.evaluate_condition(
            snapshot,
            allow_processing=allow_vm_processing,
        )
        for vm in vm_alerts:
            subject = f"{vm['name']} detenida en Proxmox"
            body = (
                f"{vm['name']} (ID {vm['vmid']}) presenta estado '{vm['status_display']}' "
                f"desde hace al menos {config.ALARM_MIN_SUSTAINED_DURATION_MINUTES} minutos."
            )
            self._send_notification_and_log(
                subject,
                body,
                config.ALARM_EMAIL_RECIPIENT,
                alarm_key=f"proxmox:vm:{vm['vmid']}",
            )

    def _process_charito_alarms(self, snapshot):
        if not isinstance(snapshot, dict):
            snapshot = {}

        items = snapshot.get("items")
        if isinstance(items, list):
            current_instance_ids = {
                str(item.get("instanceId") or item.get("alias") or "").strip()
                for item in items
                if isinstance(item, dict)
                and str(item.get("instanceId") or item.get("alias") or "").strip()
            }
            for active_key in alarm_incidents_dao.active_keys("charito:"):
                instance_id = active_key.split(":", 1)[1]
                if instance_id not in current_instance_ids:
                    self._observe_alarm_condition(active_key, False)

        for daemon in self.charito_notifier.evaluate_condition(snapshot):
            alias = daemon.get("alias") or daemon.get("instance_id") or "charo-daemon"
            instance_id = daemon.get("instance_id") or alias
            status_display = daemon.get("status_display", "OFFLINE")
            received_at = daemon.get("received_at")
            data_error = daemon.get("data_error")
            if daemon.get("status") == "offline":
                subject = f"charo-daemon {alias} offline"
                first_line = (
                    f"El demonio {alias} (ID {instance_id}) no responde desde hace al menos "
                    f"{config.ALARM_MIN_SUSTAINED_DURATION_MINUTES} minutos."
                )
            else:
                subject = f"charo-daemon {alias} en error"
                first_line = (
                    f"El demonio {alias} (ID {instance_id}) responde pero presenta estado "
                    f"'{status_display}' desde hace al menos "
                    f"{config.ALARM_MIN_SUSTAINED_DURATION_MINUTES} minutos."
                )
            body_lines = [first_line]
            if data_error:
                body_lines.append(f"Detalle detectado: {data_error}")
            if received_at:
                body_lines.append(f"Ultima actualizacion registrada: {received_at}")
            self._send_notification_and_log(
                subject,
                "\n".join(body_lines),
                config.ALARM_EMAIL_RECIPIENT,
                alarm_key=f"charito:{instance_id}",
            )

    @staticmethod
    def _alarm_metadata(alarm_key: str, title: str | None = None) -> dict:
        if alarm_key == "mw-global":
            category = "middleware_global"
            fallback_title = "Middleware - conectividad global"
        elif alarm_key.startswith("mw-node:"):
            category = "middleware_grd"
            fallback_title = f"GRD {alarm_key.split(':', 1)[1]} sin conexion"
        elif alarm_key == "modem-link":
            category = "router"
            fallback_title = "Router telefonico no alcanzable"
        elif alarm_key.startswith("ge:"):
            category = "generador"
            fallback_title = f"Generador {alarm_key.split(':', 1)[1]}"
        elif alarm_key == "proxmox:host":
            category = "proxmox_host"
            fallback_title = "Hipervisor Proxmox no responde"
        elif alarm_key.startswith("proxmox:vm:"):
            category = "proxmox_vm"
            fallback_title = f"VM Proxmox {alarm_key.rsplit(':', 1)[1]} detenida"
        elif alarm_key.startswith("charito:"):
            category = "charito"
            fallback_title = f"charo-daemon {alarm_key.split(':', 1)[1]}"
        else:
            raise ValueError(f"Categoria de alarma desconocida: {alarm_key}")
        if category not in config.ALARM_CLEARANCE_ESTIMATES_MINUTES:
            raise EnvironmentError(
                f"Falta estimacion de despeje para categoria de alarma: {category}"
            )
        return {
            "title": title or fallback_title,
            "category": category,
            "expected_clearance_minutes": config.ALARM_CLEARANCE_ESTIMATES_MINUTES[category],
        }

    def _observe_alarm_condition(self, alarm_key: str, condition_active: bool) -> None:
        if alarm_incidents_dao.observe_condition(
            alarm_key,
            condition_active,
            config.ALARM_MIN_RECOVERY_DURATION_MINUTES,
            self._alarm_metadata(alarm_key),
        ):
            self.logger.log(
                f"Incidencia resuelta: {alarm_key}.",
                origin="ALRM/LIFECYCLE",
            )

    def _send_notification_and_log(
        self,
        subject: str,
        body: str,
        recipient: List[str],
        alarm_key: str | None = None,
    ):
        """
        Encola el email y registra el intento.

        Las alarmas activas reutilizan su ID durable. Los eventos puntuales
        reciben un ID nuevo por invocacion.
        """
        incident_id = (
            alarm_incidents_dao.prepare_notification(
                alarm_key,
                self._alarm_metadata(alarm_key, subject),
            )
            if alarm_key
            else str(uuid.uuid4())
        )
        if incident_id is None:
            self.logger.log(
                f"Notificacion duplicada suprimida para incidencia activa: {alarm_key}.",
                origin="ALRM/LIFECYCLE",
            )
            return

        ok = False
        msg = ""
        try:
            ok, msg = self.mail_client.enqueue_email(
                recipients=recipient,
                subject=f"{config.ALARM_EMAIL_SUBJECT_PREFIX}{subject}",
                body=body,
                message_type="alarm_event",
                idempotency_key=incident_id,
            )
            if ok:
                if alarm_key:
                    alarm_incidents_dao.mark_notified(alarm_key, incident_id)
                self.logger.log(
                    f"ALARMA DISPARADA: {subject}. Pedido aceptado por mensagelo. "
                    f"Destinatarios: {', '.join(recipient)}",
                    origin="ALRM/EXP",
                )
            else:
                self.logger.log(
                    f"ERROR mensagelo no acepto el pedido para: {subject}. Detalle: {msg}",
                    origin="ALRM/EXP",
                )
        except Exception as exc:
            self.logger.log(f"ERROR al encolar email de alarma: {exc}", origin="ALRM/EXP")

        mensajes_enviados_dao.insert_sent_message(
            subject=subject,
            body=body,
            timestamp=timebox.utc_iso(),
            message_type="alarm_event",
            recipients=recipient,
            success=ok,
        )
        bus.publish_email_event(subject, ok)
