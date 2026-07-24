# modem-link-monitor

Servicio FastAPI que monitorea el puerto 40000 del modem remoto mediante
check-host.net y publica su estado en MQTT.

## Flujo

1. `TcpProbe` inicia un chequeo TCP externo por HTTPS y determina abierto o cerrado.
2. `ConnectionState` conserva el ultimo valor y su timestamp.
3. `MqttPublisher` publica en `config.STATUS_TOPIC`; si el broker no esta
   disponible reintenta con backoff exponencial y deja pendiente un anuncio
   `desconocido`.
4. `GET /status` entrega la vista mas reciente.

## Variables clave

- `TARGET_IP` y `TARGET_PORT`.
- Parametros de check-host: `CHECK_HOST_BASE_URL`, `CHECK_HOST_MAX_NODES`,
  `CHECK_HOST_SUCCESS_LATENCY_SECONDS`, `CHECK_HOST_RESULT_TIMEOUT_SECONDS`,
  `CHECK_HOST_POLL_INTERVAL_SECONDS` y `CHECK_HOST_REQUEST_TIMEOUT_SECONDS`.
- `PROBE_INTERVAL_SECONDS`.
- Credenciales MQTT y variables `MQTT_TOPIC_MODEM_CONEXION`,
  `MQTT_PUBLISH_QOS_STATE`, `MQTT_PUBLISH_RETAIN_STATE` y
  `MQTT_MODEM_MONITOR_CLIENT_ID`.

## Endpoints

- `GET /status` devuelve `{ip, port, state, ts}`.

El contenedor usa `./modem-link-monitor/src` y no persiste datos.
