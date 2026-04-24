import dash
from dash import dcc, html
from dash.dependencies import Input, Output, State
import plotly.graph_objects as go
import pandas as pd
from datetime import timedelta
from src.utils import timebox
from src.web.clients.modbus_client import modbus_client

BUTTON_CLASS_DEFAULT = 'button-default'
BUTTON_CLASS_ACTIVE = 'button-active'
STATE_TEXT_MAP = {0: "Desconectado", 1: "Conectado"}

def get_controls_and_graph_layout():
    """
    Define el layout para los controles (botones de tiempo, paginacion)
    y el grafico principal de conexion.
    """
    return html.Div(className='controls-and-graph-container', children=[
        # Contenedor para Botones de Tiempo/Paginacion
        html.Div(className='controls-panel', children=[
            html.Div(className='time-buttons-wrapper-outer', children=[
                html.Label("Ventana de Datos", className='control-label'),
                html.Div(className='time-buttons-wrapper-inner', children=[
                    html.Button('1 Sem', id='1sem-btn', n_clicks=0, className=BUTTON_CLASS_ACTIVE),
                    html.Button('1 Mes', id='1mes-btn', n_clicks=0, className=BUTTON_CLASS_DEFAULT),
                    html.Button('Todo', id='todo-btn', n_clicks=0, className=BUTTON_CLASS_DEFAULT),
                ]),
                html.Div(id='pagination-controls', className='pagination-controls-container', children=[
                    html.Button('Anterior', id='prev-btn', n_clicks=0, className='pagination-button'),
                    html.Button('Siguiente', id='next-btn', n_clicks=0, className='pagination-button'),
                ]),
            ]),
        ]),

        # Contenedor para el Grafico Principal
        html.Div(className='main-graph-section', children=[
            # Mensaje de advertencia para estados sin GRD disponible
            html.Div(id='no-grd-warning', className='no-grd-warning',
                     children=""),
            # Grafico principal del estado 'conectado'
            dcc.Graph(
                id='connected-wave-graph',
                className='connected-graph-container',                
            ),
        ]),
    ])


def register_controls_and_graph_callbacks(app: dash.Dash):
    """
    Registra los callbacks relacionados con los controles de seleccion
    y el grafico principal de conexion.
    """

    @app.callback(
        Output('time-window-state', 'data'),
        Output('1sem-btn', 'className'),
        Output('1mes-btn', 'className'),
        Output('todo-btn', 'className'),
        [Input('1sem-btn', 'n_clicks'),
         Input('1mes-btn', 'n_clicks'),
         Input('todo-btn', 'n_clicks'),
         Input('grd-id-dropdown', 'value')],
        [State('time-window-state', 'data')]
    )
    def set_time_window_and_grd(n_1sem, n_1mes, n_todo, selected_grd_id_from_dropdown, current_state_data):
        ctx = dash.callback_context
        triggered_id = ctx.triggered[0]['prop_id'].split('.')[0] if ctx.triggered else None

        new_state = current_state_data.copy()

        if not triggered_id or triggered_id == 'grd-id-dropdown':
            new_state['page_number'] = 0
            if triggered_id == 'grd-id-dropdown':
                new_state['current_grd_id'] = selected_grd_id_from_dropdown

        if triggered_id == '1sem-btn':
            new_state['time_window'] = '1sem'
            new_state['page_number'] = 0
        elif triggered_id == '1mes-btn':
            new_state['time_window'] = '1mes'
            new_state['page_number'] = 0
        elif triggered_id == 'todo-btn':
            new_state['time_window'] = 'todo'
            new_state['page_number'] = 0

        if triggered_id != 'grd-id-dropdown':
            new_state['current_grd_id'] = selected_grd_id_from_dropdown

        class_1sem = BUTTON_CLASS_ACTIVE if new_state['time_window'] == '1sem' else BUTTON_CLASS_DEFAULT
        class_1mes = BUTTON_CLASS_ACTIVE if new_state['time_window'] == '1mes' else BUTTON_CLASS_DEFAULT
        class_todo = BUTTON_CLASS_ACTIVE if new_state['time_window'] == 'todo' else BUTTON_CLASS_DEFAULT

        return new_state, class_1sem, class_1mes, class_todo

    @app.callback(
        Output('time-window-state', 'data', allow_duplicate=True),
        [Input('prev-btn', 'n_clicks'),
         Input('next-btn', 'n_clicks')],
        [State('time-window-state', 'data')],
        prevent_initial_call=True
    )
    def navigate_pages(n_prev, n_next, current_state_data):
        ctx = dash.callback_context
        if not ctx.triggered:
            raise dash.exceptions.PreventUpdate

        button_id = ctx.triggered[0]['prop_id'].split('.')[0]

        new_state = current_state_data.copy()
        time_window = new_state['time_window']
        page_number = new_state['page_number']
        grd_id = new_state['current_grd_id']

        if grd_id is None or time_window == 'todo':
            raise dash.exceptions.PreventUpdate

        try:
            history_meta = modbus_client.get_history(grd_id, time_window, page_number)
            total_segments = int(history_meta.get("total_periods", 0))
        except Exception:
            total_segments = 0

        if total_segments <= 0:
            raise dash.exceptions.PreventUpdate

        if button_id == 'prev-btn':
            if page_number < total_segments - 1:
                new_state['page_number'] = page_number + 1
            else:
                raise dash.exceptions.PreventUpdate
        elif button_id == 'next-btn':
            if page_number > 0:
                new_state['page_number'] = page_number - 1
            else:
                raise dash.exceptions.PreventUpdate

        return new_state

    @app.callback(
        Output('pagination-controls', 'style'),
        Output('prev-btn', 'disabled'),
        Output('next-btn', 'disabled'),
        [Input('time-window-state', 'data')]
    )
    def update_pagination_controls(time_window_state_data):
        time_window = time_window_state_data['time_window']
        page_number = time_window_state_data['page_number']
        grd_id = time_window_state_data['current_grd_id']

        if time_window == 'todo' or grd_id is None:
            return {'display': 'none'}, True, True

        try:
            history_meta = modbus_client.get_history(grd_id, time_window, page_number)
            total_segments = int(history_meta.get("total_periods", 0))
        except Exception:
            total_segments = 0

        if total_segments <= 1:
            return {'display': 'flex', 'justifyContent': 'center', 'gap': '1rem'}, True, True

        prev_disabled = (page_number == total_segments - 1)
        next_disabled = (page_number == 0)

        return {'display': 'flex', 'justifyContent': 'center', 'gap': '1rem'}, prev_disabled, next_disabled


    @app.callback(
        Output('connected-wave-graph', 'figure'),
        Output('no-grd-warning', 'children'), # Actualizamos el mensaje de advertencia del grafico
        [Input('time-window-state', 'data'),
         Input('interval-component', 'n_intervals'), # Se sigue actualizando con el intervalo
         Input('connected-wave-graph', 'relayoutData')]
    )
    def update_connected_wave_graph(time_window_state_data, n_intervals, relayout_data):
        selected_grd_id = time_window_state_data['current_grd_id']

        try:
            current_db_grd_descriptions = modbus_client.get_descriptions()
        except Exception:
            current_db_grd_descriptions = {}

        if not current_db_grd_descriptions:
            no_grd_message = "ADVERTENCIA: No se han encontrado equipos GRD en la base de datos para consulta."
            fig = go.Figure(data=[], layout=go.Layout(
                title={'text': no_grd_message, 'font': dict(family="Inter", size=20, color="#333")},
                xaxis={'visible': False}, yaxis={'visible': False}, height=400,
                font=dict(family="Inter", size=14, color="#333")
            ))
            return fig, no_grd_message # Retornamos el mensaje para el Div de advertencia

        if selected_grd_id is None:
            default_message = "Por favor, seleccione un equipo GRD del menu desplegable."
            fig = go.Figure(data=[], layout=go.Layout(
                title={'text': default_message, 'font': dict(family="Inter", size=20, color="#333")},
                xaxis={'visible': False}, yaxis={'visible': False}, height=400,
                font=dict(family="Inter", size=14, color="#333")
            ))
            return fig, default_message # Retornamos el mensaje para el Div de advertencia


        time_window = time_window_state_data['time_window']
        page_number = time_window_state_data['page_number']

        xaxis_tickformat = "%d/%m/%y %H:%M"
        xaxis_dtick = None
        xaxis_tickangle = 0
        try:
            history_payload = modbus_client.get_history(selected_grd_id, time_window, page_number)
        except Exception:
            history_payload = {
                "data": [],
                "connected_before": 0,
                "range_start": timebox.utc_iso(),
                "range_end": timebox.utc_iso(),
            }
        df = pd.DataFrame(history_payload.get('data', []))
        if not df.empty:
            df = df.sort_values(by='timestamp').reset_index(drop=True)
            df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True)

        if time_window == '1sem':
            grd_title_period = f"Semana {page_number + 1}"
        elif time_window == '1mes':
            grd_title_period = f"Mes {page_number + 1}"
            xaxis_tickformat = "%d/%m/%y"
        else:
            grd_title_period = "Todos los Datos"
            xaxis_tickformat = "%m/%y"
            xaxis_dtick = "M1"
            xaxis_tickangle = 0

        grd_description_for_title = current_db_grd_descriptions.get(selected_grd_id)
        grd_title_text = f"Historico de Conexion - {grd_title_period}" if grd_description_for_title else f"Historico de Conexion - GRD {selected_grd_id} - {grd_title_period}"

        traces = []
        shapes = []
        plot_x_line = []
        plot_y_line = []
        custom_hover_data_for_line = []

        try:
            plot_start_time = timebox.parse(history_payload.get("range_start"), legacy=True)
        except Exception:
            plot_start_time = timebox.utc_now() - timedelta(days=30)
        try:
            plot_end_time = timebox.parse(history_payload.get("range_end"), legacy=True)
        except Exception:
            plot_end_time = timebox.utc_now()

        def _format_local(dt_value):
            try:
                return timebox.format_local(dt_value, legacy=True)
            except Exception:
                return str(dt_value)

        if not df.empty:
            current_state_for_plot = int(history_payload.get("connected_before", 0))

            plot_x_line.append(plot_start_time)
            plot_y_line.append(current_state_for_plot)
            custom_hover_data_for_line.append((_format_local(plot_start_time), STATE_TEXT_MAP[current_state_for_plot]))

            for i in range(len(df)):
                current_ts_data_point = df['timestamp'].iloc[i]
                current_val_data_point = df['conectado'].iloc[i]

                segment_start_time = plot_x_line[-1]
                segment_end_time = current_ts_data_point

                if segment_start_time < segment_end_time:
                    shapes.append(
                        dict(
                            type="rect", xref="x", yref="y",
                            x0=segment_start_time, y0=0, x1=segment_end_time, y1=1,
                            fillcolor='#28a745' if current_state_for_plot == 1 else '#dc3545',
                            opacity=0.4, layer="below", line_width=0,
                        )
                    )

                plot_x_line.append(current_ts_data_point)
                plot_y_line.append(current_state_for_plot)
                custom_hover_data_for_line.append((_format_local(plot_x_line[-1]), STATE_TEXT_MAP[current_state_for_plot]))

                plot_x_line.append(current_ts_data_point)
                plot_y_line.append(current_val_data_point)
                custom_hover_data_for_line.append((_format_local(current_ts_data_point), STATE_TEXT_MAP[current_val_data_point]))

                current_state_for_plot = current_val_data_point

            if plot_x_line[-1] < plot_end_time:
                shapes.append(
                    dict(
                        type="rect", xref="x", yref="y",
                        x0=plot_x_line[-1], y0=0, x1=plot_end_time, y1=1,
                        fillcolor='#28a745' if current_state_for_plot == 1 else '#dc3545',
                        opacity=0.4, layer="below", line_width=0,
                    )
                )
                plot_x_line.append(plot_end_time)
                plot_y_line.append(current_state_for_plot)
                custom_hover_data_for_line.append((_format_local(plot_end_time), STATE_TEXT_MAP[current_state_for_plot]))

            traces.append(
                go.Scatter(
                    x=plot_x_line, y=plot_y_line, mode='lines',
                    line=dict(color='rgba(0,0,0,0)', width=0),
                    name='Estado de Conexion', customdata=custom_hover_data_for_line,
                    hovertemplate="<b>Fecha/Hora:</b> %{customdata[0]}<br><b>Estado:</b> %{customdata[1]}<extra></extra>"
                )
            )
        else:
            default_val = int(history_payload.get("connected_before", 0))
            default_local_start = _format_local(plot_start_time)
            default_local_end = _format_local(plot_end_time)
            traces.append(
                go.Scatter(
                    x=[plot_start_time, plot_end_time], y=[default_val, default_val], mode='lines',
                    line=dict(color='rgba(0,0,0,0)', width=0), name='Sin Datos / Estado Anterior',
                    customdata=[(default_local_start, STATE_TEXT_MAP[default_val]), (default_local_end, STATE_TEXT_MAP[default_val])],
                    hovertemplate="<b>Fecha/Hora:</b> %{customdata[0]}<br><b>Estado:</b> %{customdata[1]}<extra></extra>"
                )
            )
            shapes.append(
                dict(
                    type="rect", xref="x", yref="y",
                    x0=plot_start_time, y0=0, x1=plot_end_time, y1=1,
                    fillcolor='#28a745' if default_val == 1 else '#dc3545',
                    opacity=0.2, layer="below", line_width=0,
                )
            )

        fig = go.Figure(data=traces, layout={'shapes': shapes})

        ctx = dash.callback_context
        triggered_id = ctx.triggered[0]['prop_id'].split('.')[0] if ctx.triggered else 'initial_load'

        reset_zoom = False
        if triggered_id in ['grd-id-dropdown', '1sem-btn', '1mes-btn', 'todo-btn']:
            reset_zoom = True

        if relayout_data and 'xaxis.range[0]' in relayout_data and 'xaxis.range[1]' in relayout_data and not reset_zoom:
            fig.update_xaxes(range=[relayout_data['xaxis.range[0]'], relayout_data['xaxis.range[1]']])
        else:
            fig.update_xaxes(range=[plot_start_time, plot_end_time])

        fig.update_layout(
            title={'text': grd_title_text, 'font': dict(size=20, family="Inter", color="#333")},
            xaxis_title='Fecha y Hora', yaxis_title='Estado',
            yaxis=dict(
                tickmode='array', tickvals=[0.25, 0.75], ticktext=['Desconectado', 'Conectado'],
                range=[-0.1, 1.1],
                fixedrange=True
            ),
            height=300,
            plot_bgcolor='#f8f9fa', paper_bgcolor='#ffffff',
            margin=dict(l=40, r=40, t=80, b=40), font=dict(family="Inter", size=12, color="#333"),            
        )

        # Aqui siempre devolvemos un mensaje vacio para el div de advertencia
        # ya que el manejo de mensajes especificos (como "No hay datos recientes")
        # se hace directamente en el titulo del grafico si no hay GRD o no hay seleccion.
        # Solo necesitamos el mensaje si no hay GRDs en la DB al inicio.
        warning_children = "ADVERTENCIA: No se han encontrado equipos GRD en la base de datos para consulta." if not current_db_grd_descriptions else ""

        return fig, warning_children
