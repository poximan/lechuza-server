# router-telef-service

Servicio FastAPI que monitorea el puerto 40000 del módem remoto vía check-host.net y publica su estado en MQTT.

## Flujo
1. `TcpProbe` inicia un chequeo TCP externo (HTTPS verificado) y determina abierto/cerrado.
2. `ConnectionState` guarda el último valor y timestamp.
3. `MqttPublisher` publica en `config.STATUS_TOPIC`; si no hay broker disponible intenta reintentar con backoff exponencial y deja pendiente un anuncio `desconocido`.
4. `GET /status` entrega la vista más reciente.

## Variables clave
- `TARGET_IP`, `TARGET_PORT`.
- Parámetros check-host: `CHECK_HOST_BASE_URL`, `CHECK_HOST_MAX_NODES`, `CHECK_HOST_SUCCESS_LATENCY_SECONDS`, `CHECK_HOST_RESULT_TIMEOUT_SECONDS`, `CHECK_HOST_POLL_INTERVAL_SECONDS`, `CHECK_HOST_REQUEST_TIMEOUT_SECONDS`.
- `PROBE_INTERVAL_SECONDS`.
- MQTT credenciales (`MQTT_BROKER_*`, `MQTT_TOPIC_MODEM_CONEXION`, `MQTT_PUBLISH_QOS_STATE`, `MQTT_PUBLISH_RETAIN_STATE`, `MQTT_ROUTER_CLIENT_ID`).

## Endpoints
- `GET /health` (vía Uvicorn default) – opcional si se desea agregar.
- `GET /status` → `{ip, port, state, ts}`.

El contenedor usa `./router-telef-service/src` y no persiste datos.

