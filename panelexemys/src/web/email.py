from __future__ import annotations

import time
import dash
from dash import dcc, html
from dash.dependencies import Input, Output

from src.utils.paths import load_observar
from src.servicios.email.mensagelo_client import MensageloClient
from src.servicios.mqtt import mqtt_event_bus
from src.utils import timebox
import config


def get_email_layout() -> html.Div:
    """
    Retorna el layout HTML para la pagina de monitoreo y pruebas de correo.
    """
    return html.Div(
        children=[
            html.H1("Estado de Correo", className="main-title"),
            html.Div(
                className="kpi-item",
                children=[
                    html.H2("Servidor de correo", className="sub-title"),
                    html.Div(
                        className="email-health-grid",
                        children=[
                            html.Div(
                                className="email-health-item",
                                children=[
                                    html.Div(
                                        f"SMTP configurado ({config.EMAIL_HEALTH_SMTP_HOST})",
                                        className="email-health-label",
                                    ),
                                    html.Div(
                                        "desconocido",
                                        id="cell-smtp",
                                        className="email-health-value",
                                    ),
                                ],
                            ),
                            html.Div(
                                className="email-health-item",
                                children=[
                                    html.Div(
                                        f"Ping host local ({config.EMAIL_HEALTH_PING_LOCAL_HOST})",
                                        className="email-health-label",
                                    ),
                                    html.Div(
                                        "desconocido",
                                        id="cell-ping-local",
                                        className="email-health-value",
                                    ),
                                ],
                            ),
                            html.Div(
                                className="email-health-item",
                                children=[
                                    html.Div(
                                        f"Ping host remoto ({config.EMAIL_HEALTH_PING_REMOTE_HOST})",
                                        className="email-health-label",
                                    ),
                                    html.Div(
                                        "desconocido",
                                        id="cell-ping-remoto",
                                        className="email-health-value",
                                    ),
                                ],
                            ),
                        ],
                    ),
                    dcc.Interval(
                        id="email-health-interval",
                        interval=config.DASH_REFRESH_SECONDS,
                        n_intervals=0,
                    ),
                ],
                style={"marginBottom": "24px"},
            ),
            html.Div(
                className="button-container",
                children=[
                    html.Button(
                        "Probar Email (async)",
                        id="btn-probar-email",
                        n_clicks=0,
                        className="button-primary",
                    ),
                    html.Div(id="output-probar-email", style={"marginTop": "10px"}),
                ],
                style={"textAlign": "center", "marginTop": "20px"},
            ),
        ]
    )


def register_email_callbacks(app: dash.Dash, key) -> None:
    """
    Registra callbacks encargados de la prueba y el monitoreo del servidor de correo.
    """

    @app.callback(
        Output("output-probar-email", "children"),
        Input("btn-probar-email", "n_clicks"),
    )
    def handle_probar_email(n_clicks: int):
        if n_clicks <= 0:
            return ""

        test_recipient = config.ALARM_EMAIL_RECIPIENT
        origin_label = "Panelexemys - backend"
        test_subject = f"Email de Prueba ({origin_label})"
        prefixed_subject = f"{config.ALARM_EMAIL_SUBJECT_PREFIX}{test_subject}"
        test_body = (
            f"Este es un email de prueba enviado desde {origin_label}. "
            f"Fecha y Hora: {timebox.format_local(timebox.utc_now())}"
        )

        try:
            client = MensageloClient(
                base_url=config.MENSAGELO_BASE_URL,
                api_key=key,
                timeout_seconds=int(config.MENSAGELO_TIMEOUT_SECONDS),
                max_retries=int(config.MENSAGELO_MAX_RETRIES),
                backoff_initial=float(config.MENSAGELO_BACKOFF_INITIAL),
                backoff_max=float(config.MENSAGELO_BACKOFF_MAX),
            )
            ok, msg = client.enqueue_email(
                recipients=test_recipient,
                subject=prefixed_subject,
                body=test_body,
                message_type="maintenance_test",
            )
        except Exception as exc:  # pragma: no cover - logging defensivo
            ok, msg = False, f"error al contactar mensagelo: {exc}"
        try:
            mqtt_event_bus.publish_email_event(
                subject=prefixed_subject,
                ok=ok,
            )
        except Exception:
            pass

        if ok:
            return html.Div(
                [
                    html.P(
                        "Pedido aceptado por mensagelo (cola async).",
                        className="info-message",
                        style={"color": "green"},
                    ),
                    html.P(
                        f"Destinatarios: {test_recipient}",
                        style={"fontSize": "14px"},
                    ),
                    html.P(
                        f"Detalle: {msg}",
                        style={"fontSize": "12px", "color": "#333"},
                    ),
                ]
            )

        return html.Div(
            [
                html.P(
                    "No se pudo encolar el email de prueba.",
                    className="info-message",
                    style={"color": "red"},
                ),
                html.P(
                    f"Destinatarios: {test_recipient}",
                    style={"fontSize": "14px"},
                ),
                html.P(
                    f"Detalle: {msg}",
                    style={"fontSize": "12px", "color": "#333"},
                ),
            ]
        )

    @app.callback(
        Output("cell-smtp", "children"),
        Output("cell-smtp", "className"),
        Output("cell-ping-local", "children"),
        Output("cell-ping-local", "className"),
        Output("cell-ping-remoto", "children"),
        Output("cell-ping-remoto", "className"),
        Input("email-health-interval", "n_intervals"),
    )
    def update_email_health(_n_intervals: int):
        data = load_observar()
        estados = data.get("server_email_estado", {}) if isinstance(data, dict) else {}

        smtp = estados.get("smtp", "desconocido")
        ping_local = estados.get("ping_local", "desconocido")
        ping_remoto = estados.get("ping_remoto", "desconocido")

        def status_class(value: str) -> str:
            normalized = str(value).strip().lower()
            if normalized == "conectado":
                return "email-health-value email-health-value--ok"
            return "email-health-value email-health-value--bad"

        return (
            smtp,
            status_class(smtp),
            ping_local,
            status_class(ping_local),
            ping_remoto,
            status_class(ping_remoto),
        )



