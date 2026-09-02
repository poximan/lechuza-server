from __future__ import annotations

from typing import Any, Callable

from flask import Blueprint, jsonify

import config
from src.dao.dao_email_health import EmailHealthDao
from src.dao.dao_mantenimiento import MantenimientoDao
from src.dao.dao_mensagelo_attempts import MensageloAttemptsDao
from src.dao.dao_proxmox_view import ProxmoxViewDao
from src.servicios.broker.broker_service import BrokerService
from src.servicios.charito.charito_service import CharitoService
from src.servicios.email.email_service import EmailService
from src.servicios.generadores.generadores_service import GeneradoresService
from src.servicios.mantenimiento.mantenimiento_service import MantenimientoService
from src.servicios.mensagelo.mensagelo_service import MensageloService
from src.servicios.overview.overview_service import OverviewService
from src.servicios.proxmox.proxmox_service import ProxmoxService
from src.servicios.reles.reles_service import RelesService
from src.web.broker_api import BrokerApi
from src.web.charito_api import CharitoApi
from src.web.clients.charito_client import CharitoClient
from src.web.clients.modbus_client import modbus_client
from src.web.clients.modem_link_monitor_client import modem_link_monitor_client
from src.web.clients.proxmox_client import ProxmoxClient
from src.web.email_api import EmailApi
from src.web.generadores_api import GeneradoresApi
from src.web.mantenimiento_api import MantenimientoApi
from src.web.mensagelo_api import MensageloApi
from src.web.navigation import panelexemys_navigation
from src.web.overview_api import OverviewApi
from src.web.proxmox_api import ProxmoxApi
from src.web.reles_api import RelesApi


class ReactApi:
    """Registra rutas generales y conecta cada vista con su controlador propio."""

    def __init__(self, mqtt_client_manager: Any):
        charito_client = CharitoClient(config.CHARITO_API_BASE)
        proxmox_client = ProxmoxClient(config.PVE_API_BASE)
        self.overview_api = OverviewApi(
            service=OverviewService(
                modbus_client=modbus_client,
                modem_client=modem_link_monitor_client,
            ),
            require_protected=self._require_protected,
            response=self._response,
        )
        self.charito_api = CharitoApi(
            service=CharitoService(charito_client),
            require_protected=self._require_protected,
            response=self._response,
        )
        self.generadores_api = GeneradoresApi(
            service=GeneradoresService(modbus_client),
            response=self._response,
        )
        self.proxmox_api = ProxmoxApi(
            service=ProxmoxService(
                client=proxmox_client,
                view_dao=ProxmoxViewDao(),
            ),
            require_protected=self._require_protected,
            response=self._response,
        )
        self.reles_api = RelesApi(
            service=RelesService(modbus_client),
            require_protected=self._require_protected,
            response=self._response,
        )
        self.mantenimiento_api = MantenimientoApi(
            service=MantenimientoService(
                dao=MantenimientoDao(),
                public_base_url=config.PUBLIC_BASE_URL,
                topology_url="/panelexemys/topologia.png",
            ),
            require_protected=self._require_protected,
            response=self._response,
        )
        self.mensagelo_api = MensageloApi(
            service=MensageloService(MensageloAttemptsDao()),
            require_protected=self._require_protected,
            response=self._response,
        )
        self.broker_api = BrokerApi(
            service=BrokerService(mqtt_client_manager),
            require_protected=self._require_protected,
            response=self._response,
        )
        self.email_api = EmailApi(
            service=EmailService(EmailHealthDao()),
            require_protected=self._require_protected,
            response=self._response,
        )
        self.blueprint = Blueprint(
            "panelexemys-react-api",
            __name__,
            url_prefix="/panelexemys/api",
        )
        self._register_routes()

    def _register_routes(self) -> None:
        self.blueprint.add_url_rule(
            "/navigation", "navigation", self.navigation, methods=["GET"]
        )
        self.blueprint.add_url_rule(
            "/overview", "overview", self.overview_api.get, methods=["GET"]
        )
        self.blueprint.add_url_rule(
            "/grd", "grd", self.overview_api.get_grd_detail, methods=["GET"]
        )
        self.blueprint.add_url_rule(
            "/charito", "charito", self.charito_api.get, methods=["GET"]
        )
        self.blueprint.add_url_rule(
            "/generadores",
            "generadores",
            self.generadores_api.get,
            methods=["GET"],
        )
        self.blueprint.add_url_rule(
            "/proxmox", "proxmox", self.proxmox_api.get, methods=["GET"]
        )
        self.blueprint.add_url_rule(
            "/proxmox/view",
            "proxmox_view",
            self.proxmox_api.set_view,
            methods=["PUT"],
        )
        self.blueprint.add_url_rule(
            "/reles", "reles", self.reles_api.get, methods=["GET"]
        )
        self.blueprint.add_url_rule(
            "/reles/observer",
            "reles_observer",
            self.reles_api.set_observer,
            methods=["PUT"],
        )
        self.blueprint.add_url_rule(
            "/reles/<int:relay_id>/latest-disturbance",
            "rele_latest_disturbance",
            self.reles_api.latest_disturbance,
            methods=["GET"],
        )
        self.blueprint.add_url_rule(
            "/reles/<int:relay_id>/clock-snapshot",
            "rele_clock_snapshot",
            self.reles_api.clock_snapshot,
            methods=["POST"],
        )
        self.blueprint.add_url_rule(
            "/mantenimiento",
            "mantenimiento",
            self.mantenimiento_api.get,
            methods=["GET"],
        )
        self.blueprint.add_url_rule(
            "/mensagelo", "mensagelo", self.mensagelo_api.get, methods=["GET"]
        )
        self.blueprint.add_url_rule(
            "/broker", "broker", self.broker_api.get, methods=["GET"]
        )
        self.blueprint.add_url_rule(
            "/broker/connection",
            "broker_connection",
            self.broker_api.set_connection,
            methods=["PUT"],
        )
        self.blueprint.add_url_rule(
            "/email", "email", self.email_api.get, methods=["GET"]
        )
        self.blueprint.add_url_rule(
            "/email/test",
            "email_test",
            self.email_api.send_test,
            methods=["POST"],
        )

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
