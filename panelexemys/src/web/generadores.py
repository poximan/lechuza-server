from __future__ import annotations

import dash
from dash import dcc, html
from dash.dependencies import Input, Output

import config
from src.web.clients.modbus_client import modbus_client


def get_generadores_layout() -> html.Div:
    return html.Div(
        children=[
            html.H1("Generadores", className="main-title"),
            html.Div(
                className="generadores-grid",
                children=[
                    html.Div(
                        className="generador-card",
                        children=[
                            html.H2("edificio estivariz", className="generador-title"),
                            html.Div(
                                className="ge-status-card",
                                children=[
                                    html.Div(id="ge-emar-led", className="status-circle ge-led-unknown"),
                                    html.Div(id="ge-emar-text", className="ge-status-text", children="GE sin datos"),
                                ],
                            ),
                        ],
                    ),
                    html.Div(
                        className="generador-card",
                        children=[
                            html.H2("edificio fontana", className="generador-title"),
                            html.Div("proximamente", className="generador-placeholder"),
                        ],
                    ),
                ],
            ),
            dcc.Interval(
                id="ge-emar-interval",
                interval=config.DASH_REFRESH_SECONDS,
                n_intervals=0,
            ),
        ]
    )


def register_generadores_callbacks(app: dash.Dash) -> None:
    @app.callback(
        Output("ge-emar-text", "children"),
        Output("ge-emar-led", "className"),
        Input("ge-emar-interval", "n_intervals"),
    )
    def _refresh_ge_status(_tick: int):
        try:
            data = modbus_client.get_ge_status()
            estado = str(data.get("estado", "desconocido")).strip().lower()
        except Exception:
            estado = "desconocido"

        estado_map = {
            "marcha": "GE en marcha",
            "parado": "GE parado",
            "desconocido": "GE sin datos",
        }
        led_map = {
            "marcha": "status-circle ge-led-marcha",
            "parado": "status-circle ge-led-parado",
            "desconocido": "status-circle ge-led-unknown",
        }
        return estado_map.get(estado, estado_map["desconocido"]), led_map.get(estado, led_map["desconocido"])
