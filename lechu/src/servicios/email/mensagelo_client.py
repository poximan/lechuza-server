import json
import time
from typing import List, Optional, Tuple

import requests

from src.dao.dao_mensagelo_attempts import record_mensagelo_attempt


class MensageloError(Exception):
    pass


class MensageloClient:
    """
    Cliente HTTP para mensagelo.

    Todos los reintentos de una operacion conservan Idempotency-Key. Un 202
    confirma aceptacion durable, no entrega SMTP.
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        timeout_seconds: int,
        max_retries: int,
        backoff_initial: float,
        backoff_max: float,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = int(timeout_seconds)
        self.max_retries = int(max_retries)
        self.backoff_initial = float(backoff_initial)
        self.backoff_max = float(backoff_max)
        self._send_async_url = f"{self.base_url}/send_async"

    def enqueue_email(
        self,
        recipients: List[str],
        subject: str,
        body: str,
        message_type: Optional[str],
        idempotency_key: str,
    ) -> Tuple[bool, str]:
        key = str(idempotency_key or "").strip()
        if not key:
            raise ValueError("idempotency_key es obligatorio")

        payload = {
            "recipients": recipients,
            "subject": subject,
            "body": body,
            "message_type": message_type,
        }
        headers = {
            "Content-Type": "application/json",
            "X-API-Key": self.api_key,
            "Idempotency-Key": key,
        }

        def finish(ok: bool, msg: str) -> Tuple[bool, str]:
            record_mensagelo_attempt(
                ok=ok,
                recipients=recipients,
                subject=subject,
                body=body,
                message_type=message_type,
                detail=msg,
            )
            return ok, msg

        attempt = 0
        backoff = self.backoff_initial
        while True:
            attempt += 1
            try:
                response = requests.post(
                    self._send_async_url,
                    headers=headers,
                    data=json.dumps(payload, ensure_ascii=False),
                    timeout=self.timeout,
                )
            except requests.RequestException as exc:
                if attempt <= self.max_retries:
                    time.sleep(min(backoff, self.backoff_max))
                    backoff = min(backoff * 2.0, self.backoff_max)
                    continue
                return finish(
                    False,
                    f"error de red o timeout tras {attempt} intentos: {exc}",
                )

            if response.status_code == 202:
                try:
                    data = response.json()
                except ValueError:
                    return finish(False, "respuesta 202 sin JSON valido")
                ok = bool(data.get("ok")) and bool(data.get("queued"))
                message = str(data.get("message", ""))
                return finish(ok, message or "pedido aceptado")

            if response.status_code in (401, 403):
                return finish(False, "no autorizado: ver API key")

            if response.status_code in (429, 503):
                if attempt <= self.max_retries:
                    time.sleep(min(backoff, self.backoff_max))
                    backoff = min(backoff * 2.0, self.backoff_max)
                    continue
                try:
                    detail = response.json().get("detail", "")
                except Exception:
                    detail = response.text
                return finish(False, f"servicio saturado: {detail}")

            try:
                detail = response.json()
            except Exception:
                detail = response.text
            return finish(False, f"error http {response.status_code}: {detail}")
