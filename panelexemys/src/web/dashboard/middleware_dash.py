from dash import html, dcc
from dash.dependencies import Input, Output
import config

from src.web.dashboard.middleware_kpi import get_kpi_panel_layout
from src.web.dashboard.middleware_histograma import get_controls_and_graph_layout
from src.web.dashboard.middleware_tabla import get_main_data_table_layout
from src.web.clients.router_client import router_client

def get_dashboard(db_grd_descriptions, initial_grd_value):
    """
    define layout del dashboard principal
    """
    return html.Div(children=[
        html.H1("Middleware Exemys", className='main-title', style={'fontFamily': 'Inter, sans-serif'}),

        html.Div(
            className='kpi-panel-container',
            style={'display': 'flex', 'alignItems': 'center', 'justifyContent': 'center'},
            children=[
                html.Div(
                    className='kpi-item',
                    style={'display': 'flex', 'flexDirection': 'row', 'alignItems': 'center', 'justifyContent': 'space-between', 'width': '100%'},
                    children=[
                        html.P(
                            children=[
                                html.Span(
                                    id='tcp-status-label',
                                    children="estado [sin datos] = "
                                ),
                                html.Span(
                                    id='tcp-status-text',
                                    children="desconocido",
                                    style={'fontWeight': 'bold'}
                                )
                            ],
                            style={'fontSize': '1.2rem', 'fontFamily': 'Inter, sans-serif', 'margin': '0', 'marginRight': 'auto'}
                        ),
                        html.Div(
                            style={
                                'display': 'flex',
                                'alignItems': 'center',
                                'justifyContent': 'flex-end',
                                'gap': '12px'
                            },
                            children=[
                                html.A(
                                    "Check desde afuera",
                                    href=config.MODEM_EXTERNAL_CHECK_URL,
                                    target="_blank",
                                    className='modem-link',
                                    style={'margin': '0'}
                                ),
                                html.A(
                                    "Visitar MODEM",
                                    href=config.MODEM_ADMIN_URL,
                                    target="_blank",
                                    className='modem-link',
                                    style={'margin': '0'}
                                ),
                            ]
                        ),
                    ]
                )
            ]
        ),

        get_kpi_panel_layout(),
        dcc.Store(id='time-window-state', data={'time_window': '1sem', 'page_number': 0, 'current_grd_id': initial_grd_value}),
        html.Div(
            className='grd-focus-section',
            children=[
                html.Div(
                    className='grd-focus-header',
                    children=[
                        html.Div(
                            className='grd-focus-title-block',
                            children=[
                                html.H2("Seleccionar GRD", className='grd-focus-title'),
                                html.P(
                                    "Los datos del historico y caidas corresponden al GRD seleccionado.",
                                    className='grd-focus-subtitle',
                                ),
                            ],
                        ),
                        dcc.Dropdown(
                            id='grd-id-dropdown',
                            options=[{'label': desc, 'value': _id} for _id, desc in db_grd_descriptions.items()],
                            value=initial_grd_value,
                            clearable=False,
                            placeholder="No hay equipos para seleccionar" if not db_grd_descriptions else "Seleccione un GRD",
                            className='grd-focus-dropdown'
                        ),
                    ],
                ),
                get_controls_and_graph_layout(),
                get_main_data_table_layout(),
            ],
        ),
        dcc.Interval(
            id='interval-component',
            interval=config.DASH_REFRESH_SECONDS,
            n_intervals=0
        )
    ])

def register_dashboard_callbacks(app):
    """
    registra callbacks del dashboard
    """
    @app.callback(
        Output('tcp-status-label', 'children'),
        Output('tcp-status-text', 'children'),
        Input('interval-component', 'n_intervals')
    )
    def update_tcp_status(_n_intervals):
        """
        Consulta router-telef-service para conocer el estado actual del puerto.
        """
        try:
            status_data = router_client.get_status()
            label = f"estado [{status_data['ip']}:{status_data['port']}] = "
            state = str(status_data.get("state", "desconocido"))
            return label, state
        except Exception:
            return "estado [sin datos] = ", "desconocido"
