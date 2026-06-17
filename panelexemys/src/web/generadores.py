from __future__ import annotations

from typing import Any
from urllib.parse import quote

import dash
from dash import dcc, html
from dash.dependencies import Input, Output

import config
from src.web.clients.modbus_client import modbus_client


def _breaker_svg(x: int, top: int, bottom: int, bit: int | None, label: str) -> str:
    contact_color = "#334155"
    if bit is None:
        blade = (
            f'<line x1="{x}" y1="{top}" x2="{x + 28}" y2="{bottom - 26}" '
            'stroke="#64748b" stroke-width="7" stroke-linecap="round" stroke-dasharray="8 8"/>'
            f'<text x="{x + 40}" y="{(top + bottom) // 2 + 8}" fill="#64748b" '
            'text-anchor="middle" font-family="Inter, Arial, sans-serif" font-size="30" font-weight="800">?</text>'
        )
    else:
        blade_color = "#c62828" if bit == 1 else "#2e7d32"
        if bit == 1:
            blade = f'<line x1="{x}" y1="{top}" x2="{x}" y2="{bottom}" stroke="{blade_color}" stroke-width="7" stroke-linecap="round"/>'
        else:
            blade = f'<line x1="{x}" y1="{top}" x2="{x + 34}" y2="{bottom - 30}" stroke="{blade_color}" stroke-width="7" stroke-linecap="round"/>'
    return f"""
    <g>
      <circle cx="{x}" cy="{top}" r="8" fill="#fff" stroke="{contact_color}" stroke-width="4"/>
      <circle cx="{x}" cy="{bottom}" r="8" fill="#fff" stroke="{contact_color}" stroke-width="4"/>
      {blade}
      <text x="{x - 30}" y="{(top + bottom) // 2 + 6}" class="device-tag">{label}</text>
    </g>
    """


def _single_line_svg(linea_bit: int | None, grupo_bit: int | None, alarm: bool) -> str:
    frame = "#c62828" if alarm else "#cbd5e1"
    bus = "#c62828" if alarm else "#111827"
    svg = f"""
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 760 560">
      <style>
        .label {{ fill:#1f2937; text-anchor:middle; font:700 18px Inter, Arial, sans-serif; }}
        .small-label {{ fill:#1f2937; text-anchor:middle; font:700 15px Inter, Arial, sans-serif; }}
        .device-tag {{ fill:#334155; text-anchor:middle; font:800 16px Inter, Arial, sans-serif; }}
        .wire {{ stroke:#1f2937; stroke-width:5; stroke-linecap:round; }}
        .bus {{ stroke:{bus}; stroke-width:8; stroke-linecap:round; }}
        .grid-line {{ stroke:#1f2937; stroke-width:4; stroke-linecap:round; }}
      </style>
      <rect x="1" y="1" width="758" height="558" rx="10" fill="#fff" stroke="{frame}" stroke-width="3"/>
      <text x="245" y="48" class="label">Red externa</text>
      <line x1="215" y1="96" x2="275" y2="96" class="grid-line"/>
      <line x1="228" y1="112" x2="241" y2="80" class="grid-line"/>
      <line x1="245" y1="112" x2="258" y2="80" class="grid-line"/>
      <line x1="262" y1="112" x2="275" y2="80" class="grid-line"/>
      <text x="515" y="48" class="label">Grupo electrogeno</text>
      <circle cx="515" cy="102" r="32" fill="#fff8df" stroke="#1f2937" stroke-width="4"/>
      <text x="515" y="113" fill="#1f2937" text-anchor="middle" font-family="Inter, Arial, sans-serif" font-size="32" font-weight="800">G</text>
      <line x1="245" y1="96" x2="245" y2="172" class="wire"/>
      <line x1="515" y1="134" x2="515" y2="172" class="wire"/>
      {_breaker_svg(245, 172, 244, linea_bit, "IL")}
      {_breaker_svg(515, 172, 244, grupo_bit, "IG")}
      <line x1="245" y1="244" x2="245" y2="354" class="wire"/>
      <line x1="515" y1="244" x2="515" y2="354" class="wire"/>
      <line x1="205" y1="354" x2="555" y2="354" class="bus"/>
      <text x="382" y="337" class="small-label">Barra</text>
      <line x1="382" y1="354" x2="382" y2="432" class="wire"/>
      <rect x="310" y="432" width="144" height="54" rx="6" fill="#ecfdf5" stroke="#1f2937" stroke-width="3"/>
      <text x="382" y="466" class="label">Carga</text>
    </svg>
    """
    return "data:image/svg+xml;charset=utf-8," + quote(svg)


def _generator_card(prefix: str, title: str, alt: str) -> html.Div:
    return html.Div(
        className="generador-card ge-mimic-card",
        children=[
            html.H2(title, className="generador-title"),
            html.Img(
                id=f"{prefix}-single-line-img",
                className="ge-single-line-svg",
                alt=alt,
            ),
            html.Div(
                className="ge-state-grid",
                children=[
                    html.Div(id=f"{prefix}-line-state", className="ge-state-chip"),
                    html.Div(id=f"{prefix}-generator-state", className="ge-state-chip"),
                ],
            ),
            html.Div(id=f"{prefix}-text", className="ge-status-text"),
        ],
    )


def get_generadores_layout() -> html.Div:
    return html.Div(
        children=[
            html.H1("generadores", id="generadores-main-title", className="main-title"),
            html.Div(
                className="generadores-grid",
                children=[
                    _generator_card(
                        "estivariz",
                        "edificio estivariz",
                        "Mimico unifilar de grupo electrogeno Estivariz",
                    ),
                    _generator_card(
                        "fontana",
                        "edificio fontana",
                        "Mimico unifilar de grupo electrogeno Fontana",
                    ),
                ],
            ),
            dcc.Interval(
                id="generadores-interval",
                interval=config.DASH_REFRESH_SECONDS,
                n_intervals=0,
            ),
        ]
    )


def _parse_interruptor(data: dict[str, Any], key: str) -> tuple[str, int | None]:
    item = data.get(key)
    if not isinstance(item, dict):
        raise ValueError(f"Contrato GE invalido: falta objeto {key}")

    estado = str(item.get("estado", "")).strip().lower()
    raw_bit = item.get("bit")
    if raw_bit is None and estado in {"incierto", "desconocido"}:
        return estado, None

    try:
        bit = int(raw_bit)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Contrato GE invalido: {key}.bit debe ser 0, 1 o null") from exc
    if bit not in (0, 1):
        raise ValueError(f"Contrato GE invalido: {key}.bit debe ser 0, 1 o null")

    expected = "cerrado" if bit == 1 else "abierto"
    if estado != expected:
        raise ValueError(f"Contrato GE invalido: {key}.estado no coincide con bit")
    return estado, bit


def _load_generator_status(source: str) -> tuple[str, int | None, str, int | None]:
    data = (
        modbus_client.get_ge_edif_fontana_status()
        if source == "fontana"
        else modbus_client.get_ge_edif_estivariz_status()
    )
    if not isinstance(data, dict):
        raise ValueError("Contrato GE invalido: respuesta HTTP no es objeto")
    linea_estado, linea_bit = _parse_interruptor(data, "interruptor_linea")
    grupo_estado, grupo_bit = _parse_interruptor(data, "interruptor_grupo")
    return linea_estado, linea_bit, grupo_estado, grupo_bit


def _fallback_status() -> tuple[str, int | None, str, int | None]:
    return "desconocido", None, "desconocido", None


def _label(nombre: str, estado: str) -> str:
    return f"{nombre}: interruptor {estado}"


def _build_view(linea_estado: str, linea_bit: int | None, grupo_estado: str, grupo_bit: int | None) -> tuple[str, str, str, str, str, str, bool]:
    alarm = linea_bit is not None and grupo_bit is not None and linea_bit == grupo_bit
    if alarm and linea_bit == 1:
        resumen = "Alarma: red externa y GE cerrados sobre la barra"
    elif alarm and linea_bit == 0:
        resumen = "Alarma: barra sin alimentacion"
    elif grupo_bit is None:
        resumen = f"Red externa {linea_estado}; lado grupo incierto"
    elif linea_bit == 1 and grupo_bit == 0:
        resumen = "Carga alimentada desde red externa"
    else:
        resumen = "Carga alimentada desde grupo electrogeno"

    return (
        resumen,
        _single_line_svg(linea_bit, grupo_bit, alarm),
        _label("Linea", linea_estado),
        _label("Grupo", grupo_estado),
        f"ge-state-chip ge-state-chip-{linea_estado}",
        f"ge-state-chip ge-state-chip-{grupo_estado}",
        alarm,
    )


def register_generadores_callbacks(app: dash.Dash) -> None:
    @app.callback(
        Output("estivariz-text", "children"),
        Output("estivariz-single-line-img", "src"),
        Output("estivariz-line-state", "children"),
        Output("estivariz-generator-state", "children"),
        Output("estivariz-line-state", "className"),
        Output("estivariz-generator-state", "className"),
        Output("fontana-text", "children"),
        Output("fontana-single-line-img", "src"),
        Output("fontana-line-state", "children"),
        Output("fontana-generator-state", "children"),
        Output("fontana-line-state", "className"),
        Output("fontana-generator-state", "className"),
        Output("generadores-main-title", "className"),
        Input("generadores-interval", "n_intervals"),
    )
    def _refresh_ge_status(_tick: int):
        try:
            estivariz_status = _load_generator_status("estivariz")
        except Exception:
            estivariz_status = _fallback_status()

        try:
            fontana_status = _load_generator_status("fontana")
        except Exception:
            fontana_status = _fallback_status()

        estivariz_view = _build_view(*estivariz_status)
        fontana_view = _build_view(*fontana_status)
        title_alarm = estivariz_view[-1] or fontana_view[-1]
        title_class = "main-title generadores-title-alarm" if title_alarm else "main-title"

        return (
            *estivariz_view[:-1],
            *fontana_view[:-1],
            title_class,
        )
