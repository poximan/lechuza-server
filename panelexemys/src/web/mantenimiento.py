from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dash import html

import config
from src.logger import logger

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
    return html.Div(
        children=[
            html.H1("mantenimiento", className="main-title"),
            html.Div(
                className="mantenimiento-section",
                children=[
                    html.H2("Topologia de red", className="mantenimiento-section-title"),
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
            ),
            html.Div(
                className="mantenimiento-section",
                children=[
                    html.H2("Lineas telefonicas", className="mantenimiento-section-title"),
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
            ),
            html.Div(
                className="mantenimiento-section",
                children=[
                    html.H2(
                        "Mapeo de puertos (docker <-> localhost <-> https)",
                        className="mantenimiento-section-title",
                    ),
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
            ),
        ]
    )
