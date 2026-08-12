from __future__ import annotations

import uuid
from typing import Any

import config
from src.dao.dao_email_health import EmailHealthDao
from src.servicios.email.mensagelo_client import MensageloClient
from src.servicios.mqtt import mqtt_event_bus
from src.utils import timebox


class EmailService:
    def __init__(self, health_dao: EmailHealthDao):
        self.health_dao = health_dao

    def get_contract(self) -> dict[str, Any]:
        return {
            "health": self.health_dao.load(),
            "smtp_host": config.EMAIL_HEALTH_SMTP_HOST,
            "ping_local_host": config.EMAIL_HEALTH_PING_LOCAL_HOST,
            "ping_remote_host": config.EMAIL_HEALTH_PING_REMOTE_HOST,
        }

    def send_test(self) -> dict[str, Any]:
        recipient = config.ALARM_EMAIL_RECIPIENT
        subject = (
            f"{config.ALARM_EMAIL_SUBJECT_PREFIX}"
            "Email de Prueba (Panelexemys - backend)"
        )
        body = (
            "Este es un email de prueba enviado desde Panelexemys - backend. "
            f"Fecha y Hora: {timebox.format_local(timebox.utc_now())}"
        )
        client = MensageloClient(
            base_url=config.MENSAGELO_BASE_URL,
            api_key=config.MENSAGELO_API_KEY,
            timeout_seconds=int(config.MENSAGELO_TIMEOUT_SECONDS),
            max_retries=int(config.MENSAGELO_MAX_RETRIES),
            backoff_initial=float(config.MENSAGELO_BACKOFF_INITIAL),
            backoff_max=float(config.MENSAGELO_BACKOFF_MAX),
        )
        ok, detail = client.enqueue_email(
            recipients=recipient,
            subject=subject,
            body=body,
            message_type="maintenance_test",
            idempotency_key=str(uuid.uuid4()),
        )
        event_error = None
        try:
            mqtt_event_bus.publish_email_event(subject=subject, ok=ok)
        except Exception as exc:
            event_error = f"{type(exc).__name__}: {exc}"
        return {
            "ok": ok,
            "recipients": recipient,
            "detail": detail,
            "event_error": event_error,
        }
