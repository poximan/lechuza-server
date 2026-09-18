import json
import time
from typing import List, Optional, Tuple

import requests

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
                return False, f"error de red o timeout tras {attempt} intentos: {exc}"

            if response.status_code == 202:
                try:
                    data = response.json()
                except ValueError:
                    return False, "respuesta 202 sin JSON valido"
                ok = bool(data.get("ok")) and bool(data.get("queued"))
                message = str(data.get("message", ""))
                return ok, message or "pedido aceptado"

            if response.status_code in (401, 403):
                return False, "no autorizado: ver API key"

            if response.status_code in (429, 503):
                if attempt <= self.max_retries:
                    time.sleep(min(backoff, self.backoff_max))
                    backoff = min(backoff * 2.0, self.backoff_max)
                    continue
                try:
                    detail = response.json().get("detail", "")
                except Exception:
                    detail = response.text
                return False, f"servicio saturado: {detail}"

            try:
                detail = response.json()
            except Exception:
                detail = response.text
            return False, f"error http {response.status_code}: {detail}"

    def list_messages(self, limit: int | None = None) -> list[dict]:
        requested = None if limit is None else max(1, int(limit))
        result: list[dict] = []
        page_size = min(200, requested) if requested is not None else 200
        while requested is None or len(result) < requested:
            response = requests.get(
                f"{self.base_url}/internal/messages",
                headers={"X-API-Key": self.api_key},
                params={"limit": page_size, "offset": len(result)},
                timeout=self.timeout,
            )
            response.raise_for_status()
            payload = response.json()
            items = payload.get("items") if isinstance(payload, dict) else None
            total = payload.get("total") if isinstance(payload, dict) else None
            if (
                not isinstance(items, list)
                or any(not isinstance(item, dict) for item in items)
                or type(total) is not int
            ):
                raise RuntimeError("Contrato de historial Mensagelo invalido")
            result.extend(items)
            if not items or len(result) >= total:
                break
            if requested is not None:
                page_size = min(200, requested - len(result))
        return result if requested is None else result[:requested]
