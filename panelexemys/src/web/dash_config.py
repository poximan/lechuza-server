import dash
from dash import dcc, html
from queue import Queue
from dash.dependencies import Input, Output
from flask import has_request_context, request
from src.web.clients.modbus_client import modbus_client
import config

from src.web.dashboard.middleware_dash import get_dashboard, register_dashboard_callbacks
from src.web.dashboard.middleware_kpi import register_kpi_panel_callbacks
from src.web.dashboard.middleware_histograma import register_controls_and_graph_callbacks
from src.web.dashboard.middleware_tabla import register_main_data_table_callbacks
from src.web.reles_panel import get_reles_micom_layout, register_reles_micom_callbacks
from src.web.mantenimiento import get_mantenimiento_layout, register_mantenimiento_callbacks
from src.web.email import get_email_layout, register_email_callbacks
from src.web.broker.broker_view import (
    get_broker_layout,
    register_broker_callbacks,
    initialize_broker_components,
)
from src.web.proxmox import get_proxmox_layout, register_proxmox_callbacks
from src.web.charito import get_charito_layout, register_charito_callbacks

import config

api_key = config.MENSAGELO_API_KEY
BASE = "/dash"
COOKIE_NAME = "panelexemys_mode"
MODE_SECURE = "secure"
MODE_PROTECTED = "protected"

BASE_TABS = (
    ("Dashboard", BASE),
    ("Email", f"{BASE}/email"),
    ("Proxmox", f"{BASE}/proxmox"),
    ("Charito", f"{BASE}/charito"),
)

PROTECTED_TABS = (
    ("Reles MiCOM", f"{BASE}/reles"),
    ("Mantenimiento", f"{BASE}/mantenimiento"),
    ("Broker", f"{BASE}/broker"),
)


def _current_mode() -> str:
    """Lee la cookie panelexemys_mode para determinar el modo activo."""
    if has_request_context():
        cookie_value = request.cookies.get(COOKIE_NAME, MODE_SECURE)
        if cookie_value == MODE_PROTECTED:
            return MODE_PROTECTED
    return MODE_SECURE


def _build_nav_links(mode: str) -> list:
    """Construye la barra de navegacion segun el modo actual."""
    links = [dcc.Link(label, href=href, className="nav-link") for label, href in BASE_TABS]
    if mode == MODE_PROTECTED:
        links.extend(dcc.Link(label, href=href, className="nav-link") for label, href in PROTECTED_TABS)
    links.append(html.A("Salir", href="/", className="nav-link nav-link-logout"))
    return links


def configure_dash_app(
    app: dash.Dash,
    mqtt_client_manager,
    message_queue: Queue,
    auto_start_mqtt: bool = True,
) -> None:
    """Configura el layout y los callbacks de la aplicacion Dash."""
    try:
        db_grd_descriptions = modbus_client.get_descriptions()
    except Exception:
        db_grd_descriptions = {}
    initial_grd_value = next(iter(db_grd_descriptions), None)

    initialize_broker_components(mqtt_client_manager, message_queue, auto_start=auto_start_mqtt)

    dashboard_layout = get_dashboard(db_grd_descriptions, initial_grd_value)
    reles_micom_layout = get_reles_micom_layout()
    mantenimiento_layout = get_mantenimiento_layout()
    email_layout = get_email_layout()
    broker_layout = get_broker_layout()
    charito_layout = get_charito_layout()

    def serve_layout():
        mode = _current_mode()
        navbar_links = _build_nav_links(mode)
        return html.Div(
            className="main-app-container",
            children=[
                dcc.Location(id="url", refresh=False),
                html.Div(
                    className="navbar-wrapper",
                    children=[
                        html.Button(
                            "\u2630",
                            id="nav-toggle",
                            className="nav-toggle",
                            title="Menu",
                            n_clicks=0,
                        ),
                        html.Div(
                            className="navbar",
                            id="navbar-links-container",
                            children=navbar_links,
                        ),
                        html.Div(id="nav-overlay", className="nav-overlay"),
                    ],
                ),
                html.Hr(className="navbar-separator"),
                html.Div(id="page-content"),
            ],
        )

    app.layout = serve_layout

    protected_views = {
        f"{BASE}/reles": reles_micom_layout,
        f"{BASE}/mantenimiento": mantenimiento_layout,
        f"{BASE}/broker": broker_layout,
    }

    public_views = {
        f"{BASE}/email": email_layout,
        f"{BASE}/proxmox": get_proxmox_layout,
        f"{BASE}/charito": charito_layout,
    }

    @app.callback(Output("page-content", "children"), Input("url", "pathname"))
    def display_page(pathname: str):
        mode = _current_mode()
        current_path = pathname or BASE
        if current_path.endswith("/") and current_path != "/":
            current_path = current_path.rstrip("/")
        if current_path == "/":
            current_path = BASE

        if current_path in protected_views:
            if mode != MODE_PROTECTED:
                return html.Div("Modo protegido requerido para esta pestana.", className="error-page")
            view = protected_views[current_path]
            return view() if callable(view) else view

        if current_path in public_views:
            view = public_views[current_path]
            return view() if callable(view) else view

        if current_path == BASE:
            return dashboard_layout

        return html.Div("Ruta no encontrada", className="error-page")

    register_dashboard_callbacks(app)
    register_kpi_panel_callbacks(app, config)
    register_controls_and_graph_callbacks(app)
    register_main_data_table_callbacks(app)
    register_reles_micom_callbacks(app)
    register_mantenimiento_callbacks(app)
    register_email_callbacks(app, api_key)
    register_broker_callbacks(app)
    register_proxmox_callbacks(app)
    register_charito_callbacks(app)
