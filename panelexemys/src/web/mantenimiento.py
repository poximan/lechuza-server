from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import dash
from dash import html, dcc
from dash.dependencies import Input, Output

import config
from src.logger import logger
from src.web.clients.modbus_client import modbus_client

PUBLIC_BASE_URL = config.PUBLIC_BASE_URL
SCRIPT_DIR = Path(__file__).resolve().parent
MANTENIMIENTO_DATA_PATH = SCRIPT_DIR / "mantenimiento_data.txt"


def _load_mantenimiento_data() -> dict[str, Any]:
    try:
        raw_data = MANTENIMIENTO_DATA_PATH.read_text(encoding="utf-8")
        data = json.loads(raw_data)

        telefonos = data["telefonos"]
        fontana = telefonos["fontana"]
        estivariz = telefonos["estivariz"]
        general = telefonos["general"]
        port_mappings = data["port_mappings"]

        for entries in (fontana, estivariz, general):
            for entry in entries:
                _ = entry["numero"]
                if "comentario" in entry:
                    _ = entry["comentario"]

        resolved_port_mappings = []
        for item in port_mappings:
            servicio = item["servicio"]
            interno = item["interno"]
            externo_path = item["externo_path"]
            localhost = item["localhost"]
            resolved_port_mappings.append(
                {
                    "servicio": servicio,
                    "interno": interno,
                    "externo": f"{PUBLIC_BASE_URL}{externo_path}",
                    "localhost": localhost,
                }
            )

        return {
            "telefonos": {
                "fontana": fontana,
                "estivariz": estivariz,
                "general": general,
            },
            "port_mappings": resolved_port_mappings,
        }
    except Exception as exc:
        logger.error("No se pudo cargar mantenimiento_data.txt: %s", exc, origin="MANTENIMIENTO")
        raise


MANTENIMIENTO_DATA = _load_mantenimiento_data()
TELEFONOS = MANTENIMIENTO_DATA["telefonos"]
PORT_MAPPINGS = MANTENIMIENTO_DATA["port_mappings"]


def _render_phone_item(item: dict[str, str]) -> html.Li:
    number = item["numero"]
    if "comentario" not in item:
        return html.Li(number)
    comment = item["comentario"]
    return html.Li([number, html.Span(f" ({comment})", className="telefono-comentario")])


def get_mantenimiento_layout() -> html.Div:
    """
    Layout de la pestaña de mantenimiento con estado del GE, topología, mapeos de puertos e iframe del repositorio.
    """
    return html.Div(
        children=[
            html.H1("Mantenimiento", className="main-title"),
            html.Div(
                children=[
                    html.H2("Grupo Electrogeno", className="sub-title"),
                    html.Div(
                        className="ge-status-card",
                        children=[
                            html.Div(id="ge-emar-led", className="status-circle ge-led-unknown"),
                            html.Div(id="ge-emar-text", className="ge-status-text", children="GE sin datos"),
                        ],
                    ),
                ],
                style={"marginBottom": "32px"},
            ),
            html.Div(
                children=[
                    html.H2("Topologia de red", className="sub-title"),
                    html.Div(
                        className="magnifier-container",
                        children=[
                            html.Img(
                                src="./assets/topologia.png",
                                alt="Diagrama de Topologia de la Aplicacion",
                                className="magnifier-image",
                            ),
                            html.Div(className="magnifier-loupe"),
                        ],
                        style={"width": "100%", "margin": "0 auto", "position": "relative"},
                    ),
                ],
                style={"textAlign": "center", "marginBottom": "32px"},
            ),
            html.Div(
                children=[
                    html.H2("Lineas telefonicas", className="sub-title"),
                    html.Div(
                        className="telefonos-grid",
                        children=[
                            html.Div(
                                className="telefonos-col",
                                children=[
                                    html.H3("Fontana", className="telefonos-col-title"),
                                    html.Ul(
                                        [_render_phone_item(item) for item in TELEFONOS["fontana"]],
                                        className="telefonos-list",
                                    ),
                                ],
                            ),
                            html.Div(
                                className="telefonos-col",
                                children=[
                                    html.H3("Estivariz", className="telefonos-col-title"),
                                    html.Ul(
                                        [_render_phone_item(item) for item in TELEFONOS["estivariz"]],
                                        className="telefonos-list",
                                    ),
                                ],
                            ),
                        ],
                    ),
                    html.Div(
                        className="telefonos-general",
                        children=[
                            html.H3("General", className="telefonos-col-title"),
                            html.Ul(
                                [_render_phone_item(item) for item in TELEFONOS["general"]],
                                className="telefonos-list",
                            ),
                        ],
                    ),
                ],
                style={"marginBottom": "32px"},
            ),
            html.Div(
                children=[
                    html.H2("Mapeo de puertos (docker <-> localhost <-> https)", className="sub-title"),
                    html.Table(
                        className="port-mapping-table",
                        children=[
                            html.Thead(
                                html.Tr(
                                    [
                                        html.Th("servicio"),
                                        html.Th("docker interno"),
                                        html.Th("https publico"),
                                        html.Th("localhost pruebas"),
                                    ]
                                )
                            ),
                            html.Tbody(
                                [
                                    html.Tr(
                                        [
                                            html.Td(item["servicio"]),
                                            html.Td(item["interno"]),
                                            html.Td(item["externo"]),
                                            html.Td(item["localhost"]),
                                        ]
                                    )
                                    for item in PORT_MAPPINGS
                                ]
                            ),
                        ],
                    ),
                ],
                style={"marginBottom": "32px"},
            ),
            dcc.Interval(
                id="ge-emar-interval",
                interval=config.DASH_REFRESH_SECONDS,
                n_intervals=0,
            ),
        ]
    )


def register_mantenimiento_callbacks(app: dash.Dash) -> None:
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
