# charito-service

Microservicio FastAPI que releva el estado de instancias remotas de `charo-daemon` y expone una vista consolidada para el resto de Lechuza.

## Responsabilidades

- Cargar el inventario de instancias desde `CHARITO_TARGETS_JSON`.
- Consultar periodicamente el endpoint remoto de metricas.
- Persistir el ultimo estado observado en `CHARITO_STATE_FILE`.
- Exponer una API HTTP interna para que `panelexemys` consulte estado agregado o por instancia.
- Publicar por MQTT el snapshot consolidado en `CHARITO_MQTT_STATE_TOPIC` para consumidores externos como `panelito`.

## Endpoints

- `GET /health`
- `GET /api/charito/instances`
- `GET /api/charito/instances/{instance_id}`
- `GET /api/charito/state`

## Configuracion

Variables obligatorias:

- `CHARITO_DATA_DIR`
- `CHARITO_STATE_FILE`
- `CHARITO_TARGETS_JSON`
- `CHARITO_MQTT_STATE_TOPIC`
- `MQTT_BROKER_HOST`
- `MQTT_BROKER_PORT`
- `MQTT_BROKER_USERNAME`
- `MQTT_BROKER_PASSWORD`
- `MQTT_BROKER_USE_TLS`
- `MQTT_TLS_INSECURE`
- `MQTT_BROKER_KEEPALIVE`

`CHARITO_TARGETS_JSON` debe contener un unico formato valido: un objeto JSON con `instances`, `pollIntervalSeconds` y `httpTimeoutSeconds`. Cada entrada de `instances` debe declarar `id`, `alias` y `baseUrl`. El endpoint remoto de metricas es parte fija del contrato: `/metrics`.

Contrato MQTT:

- `CHARITO_MQTT_STATE_TOPIC`, por defecto recomendado `charito/state`.
- Payload retenido: objeto JSON con `ts` e `items`.
- `charito-service` es la unica fuente de verdad del estado `charo-daemon`; los consumidores no deben suscribirse directo a `charodaemon/host/*`.
- Estados validos por instancia: `online`, `offline`, `error` y `desconocido`.
- Un daemon alcanzable pero sin metricas validas se publica como `status: "error"` con `hostReachable: true`.

## Integracion en el mono-repo

- Se construye desde la raiz de `lechuza-server` y reutiliza `shared/` dentro de la imagen.
- En `docker-compose.yml` persiste su estado en `./volumes/charito-service:/app/data`.
- No modifica ni versiona codigo de `charo-daemon`; solo consume sus contratos remotos.
