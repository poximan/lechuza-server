from dash import html, dcc, no_update, dash_table
from dash.dependencies import Input, Output, State
import dash_daq as daq
from src.utils import timebox
from src.web.clients.modbus_client import modbus_client
import config

def get_reles_micom_layout():
    """
    layout de la pestaña Reles MiCOM con switch de observacion y tabla de fallas
    """

    try:
        initial_on = bool(modbus_client.get_reles_observer())
    except Exception:
        initial_on = False

    return html.Div(children=[
        html.H1("Estado Reles MiCOM", className='main-title'),

        html.Div([
            daq.BooleanSwitch(
                id='reles-micom-observer-toggle',
                label='Observar Reles MiCOM',
                labelPosition='right',
                on=initial_on,
                style={'margin-right': '10px'}
            ),
            html.Div(id='reles-micom-observer-status', className='hidden-element')
        ], className='reles-controls-container'),

        html.Div(
            id='reles-faults-container',
            children=[html.P("Cargando datos de fallas de reles...")],
            className='reles-faults-grid-container'
        ),

        dcc.Interval(
            id='reles-faults-interval',
            interval=config.DASH_REFRESH_SECONDS,
            n_intervals=0
        )
    ])

def register_reles_micom_callbacks(app):
    """
    registra callbacks de la pestaña Reles MiCOM
    """
    @app.callback(
        Output('reles-micom-observer-status', 'children'),
        Input('reles-micom-observer-toggle', 'on')
    )
    def update_observer_status(is_observing):
        """
        persiste bandera reles_consultar en observar.json
        """
        try:
            modbus_client.set_reles_observer(bool(is_observing))
        except Exception:
            return no_update
        return no_update

    @app.callback(
        Output('reles-faults-container', 'children'),
        Input('reles-faults-interval', 'n_intervals')
    )
    def update_reles_faults_display(_n_intervals):
        """
        arma tarjetas con la ultima falla por rele activo
        """
        from dash import html  # import local para evitar dependencias circulares

        fault_tables = []

        try:
            reles_payload = modbus_client.get_reles_faults()
        except Exception:
            reles_payload = {"items": []}
        active_items = reles_payload.get("items", [])

        if not active_items:
            return html.P("No hay reles activos configurados o con descripcion 'NO APLICA'.", className="text-gray-600 mt-4")

        for item in active_items:
            modbus_id = item.get("id_modbus")
            description = item.get("description")
            latest_falla = item.get("latest") or {}

            formatted_timestamp = latest_falla.get('timestamp')
            if formatted_timestamp:
                try:
                    formatted_timestamp = timebox.format_local(formatted_timestamp, legacy=True)
                except Exception:
                    formatted_timestamp = str(formatted_timestamp)
            else:
                formatted_timestamp = "N/D"

            data_for_table = [
                {"Atributo": "ID Modbus", "Valor": modbus_id},
                {"Atributo": "Descripcion", "Valor": description},
                {"Atributo": "Numero de Falla", "Valor": latest_falla.get('numero_falla')},
                {"Atributo": "Fecha/Hora", "Valor": formatted_timestamp},
                {"Atributo": "Corriente Fase A", "Valor": latest_falla.get('fasea_corr')},
                {"Atributo": "Corriente Fase B", "Valor": latest_falla.get('faseb_corr')},
                {"Atributo": "Corriente Fase C", "Valor": latest_falla.get('fasec_corr')},
                {"Atributo": "Corriente Tierra", "Valor": latest_falla.get('tierra_corr')},
            ]

            fault_tables.append(
                html.Div([
                    dash_table.DataTable(
                        id=f'falla-table-{modbus_id}',
                        columns=[
                            {"name": "Atributo", "id": "Atributo"},
                            {"name": "Valor", "id": "Valor"}
                        ],
                        data=data_for_table,
                        style_table={'overflowX': 'auto'},
                        style_cell={'textAlign': 'left', 'fontFamily': 'Inter, sans-serif', 'padding': '8px 12px'},
                        style_header={'backgroundColor': '#66A5AD', 'color': 'white', 'fontWeight': 'bold'},
                        style_data_conditional=[
                            {
                                'if': {'row_index': 'odd'},
                                'backgroundColor': '#C4DFE6'
                            }
                        ]
                    )
                ], className="reles-fault-card")
            )

        if not fault_tables:
            return html.P("No hay datos de fallas disponibles para mostrar o no hay reles configurados.", className="text-gray-600 mt-4")

        return fault_tables

