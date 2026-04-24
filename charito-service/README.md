# charito-service

Microservicio FastAPI que releva el estado de instancias remotas de `charo-daemon` y expone una vista consolidada para el resto de Lechuza.

## Responsabilidades

- Cargar el inventario de instancias desde `CHARITO_TARGETS_JSON`.
- Consultar periodicamente los endpoints remotos de identidad y metricas.
- Persistir el ultimo estado observado en `CHARITO_STATE_FILE`.
- Exponer una API HTTP interna para que `panelexemys` consulte estado agregado o por instancia.

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
- `CHARITO_POLL_INTERVAL_SECONDS`
- `CHARITO_HTTP_TIMEOUT_SECONDS`

`CHARITO_TARGETS_JSON` debe contener un objeto JSON con `instances`, `pollIntervalSeconds` y `httpTimeoutSeconds`. Cada entrada debe declarar al menos `alias` y `baseUrl`.

## Integracion en el mono-repo

- Se construye desde la raiz de `lechuza-server` y reutiliza `shared/` dentro de la imagen.
- En `docker-compose.yml` persiste su estado en `./volumes/charito-service:/app/data`.
- No modifica ni versiona codigo de `charo-daemon`; solo consume sus contratos remotos.
