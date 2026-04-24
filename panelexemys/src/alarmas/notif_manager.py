import os
from typing import List
from src.logger import Logosaurio
from ..servicios.mqtt import mqtt_event_bus as bus
from .categorias.notif_mw_global import NotifMwGlobal
from .categorias.notif_mw_nodo import NotifMwNodo
from .categorias.notif_modem import NotifModem
from .categorias.notif_ge_emar import NotifGeEmar
from .categorias.notif_proxmox import NotifProxmoxHost, NotifProxmoxVm
from .categorias.notif_charito import NotifCharitoDaemon
from src.dao.dao_mensajes_enviados import mensajes_enviados_dao
from src.servicios.email.mensagelo_client import MensageloClient
from src.utils import timebox
from src.web.clients.modbus_client import modbus_client
from src.web.clients.group_elect_client import group_elect_client
from src.web.clients.proxmox_client import ProxmoxClient
from src.web.clients.charito_client import CharitoClient
import config

class NotifManager:
    """
    Orquestador de notificaciones:
    - Evalua condiciones (global, nodo, modem)
    - Encola email via mensagelo (asincronico, sin esperar entrega)
    - Publica evento en MQTT
    - Registra en DB local el intento de envio
    """
    def __init__(self, logger: Logosaurio, excluded_grd_ids: set, key):
        self.logger = logger
        self.global_notifier = NotifMwGlobal(logger)
        self.nodo_notifier = NotifMwNodo(logger, excluded_grd_ids)
        self.modem_notifier = NotifModem(logger)
        self.ge_notifier = NotifGeEmar(logger, group_elect_client, min_duration_seconds=60)
        self.proxmox_host_notifier = NotifProxmoxHost(logger)
        self.proxmox_vm_notifier = NotifProxmoxVm(logger)
        self.charito_notifier = NotifCharitoDaemon(logger)
        self.proxmox_client = ProxmoxClient(config.PVE_API_BASE)
        self.charito_client = CharitoClient(config.CHARITO_API_BASE)
        self.mail_client = MensageloClient(
            base_url=config.MENSAGELO_BASE_URL,
            api_key=key,
            timeout_seconds=int(config.MENSAGELO_TIMEOUT_SECONDS),
            max_retries=int(config.MENSAGELO_MAX_RETRIES),
            backoff_initial=float(config.MENSAGELO_BACKOFF_INITIAL),
            backoff_max=float(config.MENSAGELO_BACKOFF_MAX)
            )

    def run_alarm_processing(self):
        try:
            summary = modbus_client.get_summary()
        except Exception:
            summary = {"summary": {"porcentaje": 0}, "disconnected": []}
        connection_percentage = summary.get("summary", {}).get("porcentaje", 0)
        disconnected = summary.get("disconnected", [])
        self._process_alarms(connection_percentage, disconnected)
        self._process_proxmox_alarms(self._fetch_proxmox_snapshot())
        self._process_charito_alarms(self._fetch_charito_snapshot())

    def _fetch_proxmox_snapshot(self) -> dict:
        """
        Consulta directamente el servicio pve-service para obtener el estado actual del hipervisor.
        """
        try:
            snapshot = self.proxmox_client.get_state()
            if isinstance(snapshot, dict):
                return snapshot
            self.logger.log("Snapshot Proxmox invalido (no dict).", origin="ALRM/PVE")
        except Exception as exc:
            self.logger.log(f"ERROR consultando estado Proxmox: {exc}", origin="ALRM/PVE")
        return {}

    def _fetch_charito_snapshot(self) -> dict:
        """
        Consulta charito-service para obtener el estado actual de los demonios.
        """
        try:
            snapshot = self.charito_client.get_state()
            if isinstance(snapshot, dict):
                return snapshot
            self.logger.log("Snapshot charito invalido (no dict).", origin="ALRM/CHARITO")
        except Exception as exc:
            self.logger.log(f"ERROR consultando estado charito-service: {exc}", origin="ALRM/CHARITO")
        return {}

    def _process_alarms(self, current_percentage: float, disconnected_grds: list):
        if self.global_notifier.evaluate_condition(current_percentage):
            subject = "Middleware sin conexion"
            body = (
                f"Conectividad global exemys ha caido por debajo del "
                f"{config.GLOBAL_THRESHOLD_ROJO}% ({current_percentage:.2f}%) por mas de "
                f"{config.ALARM_MIN_SUSTAINED_DURATION_MINUTES} minutos.\n"
            )
            self._send_notification_and_log(subject, body, config.ALARM_EMAIL_RECIPIENT)

        grds_to_alert = self.nodo_notifier.evaluate_condition(current_percentage, disconnected_grds)
        for grd_info in grds_to_alert:
            subject = f"{grd_info['description']} sin conexion"
            body = (
                f"GRD {grd_info['description']} sin conexion por mas de "
                f"{config.ALARM_MIN_SUSTAINED_DURATION_MINUTES} minutos, "
                f"con conectividad global por encima del "
                f"{config.GLOBAL_THRESHOLD_ROJO}% ({current_percentage:.2f}%).\n"
            )
            self._send_notification_and_log(subject, body, config.ALARM_EMAIL_RECIPIENT)

        if self.modem_notifier.evaluate_condition():
            subject = "Router telef. puerto de escucha cerrado"
            body = (
                f"El modem conexion de exemys no puede ser alcanzado hace mas de "
                f"{config.ALARM_MIN_SUSTAINED_DURATION_MINUTES} minutos."
            )
            self._send_notification_and_log(subject, body, config.ALARM_EMAIL_RECIPIENT)

        if self.ge_notifier.evaluate_condition():
            subject = "edif. estivariz GE en marcha"
            body = (
                "El grupo electrogeno de edif. Estivariz se encuentra en marcha por mas de 1 minuto."
            )
            self._send_notification_and_log(subject, body, config.ALARM_EMAIL_RECIPIENT)

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
            subject = "Hipervisor Proxmox no responde"
            self._send_notification_and_log(subject, "\n".join(body_lines), config.ALARM_EMAIL_RECIPIENT)

        allow_vm_processing = self.proxmox_host_notifier.allow_vm_processing()
        vm_alerts = self.proxmox_vm_notifier.evaluate_condition(snapshot, allow_processing=allow_vm_processing)
        for vm in vm_alerts:
            subject = f"{vm['name']} detenida en Proxmox"
            body = (
                f"{vm['name']} (ID {vm['vmid']}) presenta estado '{vm['status_display']}' "
                f"desde hace al menos {config.ALARM_MIN_SUSTAINED_DURATION_MINUTES} minutos."
            )
            self._send_notification_and_log(subject, body, config.ALARM_EMAIL_RECIPIENT)

    def _process_charito_alarms(self, snapshot):
        if not isinstance(snapshot, dict):
            snapshot = {}

        daemon_alerts = self.charito_notifier.evaluate_condition(snapshot)
        for daemon in daemon_alerts:
            alias = daemon.get("alias") or daemon.get("instance_id") or "charo-daemon"
            instance_id = daemon.get("instance_id") or alias
            status_display = daemon.get("status_display", "OFFLINE")
            received_at = daemon.get("received_at")
            subject = f"charo-daemon {alias} offline"
            body_lines = [
                f"El demonio {alias} (ID {instance_id}) presenta estado '{status_display}' "
                f"desde hace al menos {config.ALARM_MIN_SUSTAINED_DURATION_MINUTES} minutos."
            ]
            if received_at:
                body_lines.append(f"Ultima actualizacion registrada: {received_at}")
            self._send_notification_and_log(subject, "\n".join(body_lines), config.ALARM_EMAIL_RECIPIENT)

    def _send_notification_and_log(self, subject: str, body: str, recipient: List[str]):
        """
        Encola el email en mensagelo y registra el intento en DB local.
        'ok' significa que mensagelo acepto el pedido (no que el SMTP lo haya entregado).
        """
        ok = False
        msg = ""
        try:
            ok, msg = self.mail_client.enqueue_email(
                recipients=recipient,
                subject=f"{config.ALARM_EMAIL_SUBJECT_PREFIX}{subject}",
                body=body,
                message_type="alarm_event",
            )
            if ok:
                self.logger.log(
                    f"ALARMA DISPARADA: {subject}. Pedido aceptado por mensagelo. Destinatarios: {', '.join(recipient)}",
                    origin="ALRM/EXP",
                )
            else:
                self.logger.log(
                    f"ERROR mensagelo no acepto el pedido para: {subject}. Detalle: {msg}",
                    origin="ALRM/EXP",
                )
        except Exception as e:
            self.logger.log(f"ERROR al encolar email de alarma: {e}", origin="ALRM/EXP")

        # Registro local en DB (usa RLock y get_db_connection del dao_base)
        mensajes_enviados_dao.insert_sent_message(
            subject=subject,
            body=body,
            timestamp=timebox.utc_iso(),
            message_type="alarm_event",
            recipients=recipient,
            success=ok
        )

        # Evento SOLO a 'estado/email' (no retain)
        bus.publish_email_event(subject, ok)

