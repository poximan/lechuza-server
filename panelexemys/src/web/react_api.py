from __future__ import annotations

import json
import threading
import uuid
from pathlib import Path
from typing import Any, Callable

from flask import Blueprint, jsonify, request

import config
from src.servicios.email.mensagelo_attempt_log import get_mensagelo_attempts
from src.servicios.email.mensagelo_client import MensageloClient
from src.servicios.mqtt import mqtt_event_bus
from src.utils import timebox
from src.utils.paths import load_observar
from src.web.clients.charito_client import CharitoClient
from src.web.clients.modbus_client import modbus_client
from src.web.clients.modem_link_monitor_client import modem_link_monitor_client
from src.web.clients.proxmox_client import ProxmoxClient
from src.web.navigation import panelexemys_navigation


class ReactApi:
    """Traduce las fuentes operativas a contratos HTTP para el frontend React."""

    def __init__(self, mqtt_client_manager: Any):
        self.mqtt_client_manager = mqtt_client_manager
        self.charito = CharitoClient(config.CHARITO_API_BASE)
        self.proxmox = ProxmoxClient(config.PVE_API_BASE)
        self.blueprint = Blueprint("panelexemys-react-api", __name__, url_prefix="/panelexemys/api")
        self._register_routes()

    def _register_routes(self) -> None:
        self.blueprint.get("/navigation")(self.navigation)
        self.blueprint.get("/overview")(self.overview)
        self.blueprint.get("/grd")(self.grd_detail)
        self.blueprint.get("/charito")(self.charito_state)
        self.blueprint.get("/generadores")(self.generator_state)
        self.blueprint.get("/proxmox")(self.proxmox_state)
        self.blueprint.get("/reles")(self.reles_state)
        self.blueprint.put("/reles/observer")(self.set_reles_observer)
        self.blueprint.get("/mantenimiento")(self.maintenance)
        self.blueprint.get("/mensagelo")(self.mensagelo_attempts)
        self.blueprint.get("/broker")(self.broker_state)
        self.blueprint.put("/broker/connection")(self.set_broker_connection)
        self.blueprint.get("/email")(self.email_state)
        self.blueprint.post("/email/test")(self.send_test_email)

    @staticmethod
    def _response(operation: Callable[[], dict[str, Any] | list[Any]]) -> Any:
        try:
            return jsonify(operation())
        except Exception as exc:
            return jsonify({"error": f"{type(exc).__name__}: {exc}"}), 502

    @staticmethod
    def _require_protected() -> Any | None:
        if panelexemys_navigation.current_mode() != panelexemys_navigation.protected_mode:
            return jsonify({"error": "protected_mode_required"}), 403
        return None

    def navigation(self) -> Any:
        mode = panelexemys_navigation.current_mode()
        return jsonify(panelexemys_navigation.contract(mode))

    def overview(self) -> Any:
        def load() -> dict[str, Any]:
            return {
                "summary": modbus_client.get_summary(),
                "descriptions": modbus_client.get_descriptions(),
                "modem": modem_link_monitor_client.get_status(),
                "links": {
                    "external_check": config.MODEM_EXTERNAL_CHECK_URL,
                    "modem_admin": config.MODEM_ADMIN_URL,
                },
            }

        return self._response(load)

    def grd_detail(self) -> Any:
        try:
            grd_id = int(request.args["grd_id"])
            window = str(request.args.get("window", "1sem"))
            page = int(request.args.get("page", "0"))
        except (KeyError, TypeError, ValueError):
            return jsonify({"error": "grd_id, window y page deben ser validos"}), 400
        if window not in {"1sem", "1mes", "todo"} or page < 0:
            return jsonify({"error": "window o page fuera de contrato"}), 400

        def load() -> dict[str, Any]:
            descriptions = modbus_client.get_descriptions()
            if grd_id not in descriptions:
                raise ValueError(f"GRD {grd_id} no existe en el catalogo")
            return {
                "grd_id": grd_id,
                "description": descriptions[grd_id],
                "window": window,
                "page": page,
                "history": modbus_client.get_history(grd_id, window, page),
                "outages": modbus_client.get_outages(grd_id, limit=10),
            }

        return self._response(load)

    def charito_state(self) -> Any:
        return self._response(self.charito.get_state)

    def generator_state(self) -> Any:
        return self._response(
            lambda: {
                "estivariz": modbus_client.get_ge_edif_estivariz_status(),
                "fontana": modbus_client.get_ge_edif_fontana_status(),
            }
        )

    def proxmox_state(self) -> Any:
        return self._response(
            lambda: {
                "state": self.proxmox.get_state(),
                "history": self.proxmox.get_history(),
            }
        )

    def reles_state(self) -> Any:
        denied = self._require_protected()
        if denied is not None:
            return denied
        return self._response(
            lambda: {
                "observer_enabled": modbus_client.get_reles_observer(),
                "faults": modbus_client.get_reles_faults(),
            }
        )

    def set_reles_observer(self) -> Any:
        denied = self._require_protected()
        if denied is not None:
            return denied
        body = request.get_json(silent=True)
        if not isinstance(body, dict) or not isinstance(body.get("enabled"), bool):
            return jsonify({"error": "enabled debe ser booleano"}), 400
        return self._response(lambda: {"enabled": modbus_client.set_reles_observer(body["enabled"])})

    def maintenance(self) -> Any:
        denied = self._require_protected()
        if denied is not None:
            return denied

        def load() -> dict[str, Any]:
            path = Path(__file__).resolve().parent / "mantenimiento_data.txt"
            data = json.loads(path.read_text(encoding="utf-8"))
            mappings = data["port_mappings"]
            return {
                "telefonos": data["telefonos"],
                "port_mappings": [
                    {
                        **item,
                        "externo": f"{config.PUBLIC_BASE_URL}{item['externo_path']}",
                    }
                    for item in mappings
                ],
            }

        return self._response(load)

    def mensagelo_attempts(self) -> Any:
        denied = self._require_protected()
        if denied is not None:
            return denied
        return jsonify({"items": get_mensagelo_attempts()})

    def broker_state(self) -> Any:
        denied = self._require_protected()
        if denied is not None:
            return denied
        return jsonify(
            {
                "status": self.mqtt_client_manager.get_connection_status(),
                "traffic": self.mqtt_client_manager.get_traffic_snapshot(),
            }
        )

    def set_broker_connection(self) -> Any:
        denied = self._require_protected()
        if denied is not None:
            return denied
        body = request.get_json(silent=True)
        if not isinstance(body, dict) or not isinstance(body.get("enabled"), bool):
            return jsonify({"error": "enabled debe ser booleano"}), 400
        if body["enabled"]:
            if self.mqtt_client_manager.get_connection_status() == "desconectado":
                threading.Thread(target=self.mqtt_client_manager.start, daemon=True).start()
        else:
            self.mqtt_client_manager.stop()
        return jsonify({"enabled": body["enabled"]})

    def email_state(self) -> Any:
        data = load_observar()
        return jsonify(
            {
                "health": data.get("server_email_estado", {}),
                "smtp_host": config.EMAIL_HEALTH_SMTP_HOST,
                "ping_local_host": config.EMAIL_HEALTH_PING_LOCAL_HOST,
                "ping_remote_host": config.EMAIL_HEALTH_PING_REMOTE_HOST,
            }
        )

    def send_test_email(self) -> Any:
        denied = self._require_protected()
        if denied is not None:
            return denied
        recipient = config.ALARM_EMAIL_RECIPIENT
        subject = f"{config.ALARM_EMAIL_SUBJECT_PREFIX}Email de Prueba (Panelexemys - backend)"
        body = (
            "Este es un email de prueba enviado desde Panelexemys - backend. "
            f"Fecha y Hora: {timebox.format_local(timebox.utc_now())}"
        )

        def send() -> dict[str, Any]:
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
            mqtt_event_bus.publish_email_event(subject=subject, ok=ok)
            return {"ok": ok, "recipients": recipient, "detail": detail}

        return self._response(send)
