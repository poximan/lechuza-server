# scada-citec-service

Microservicio FastAPI con frontend estatico que adapta un daemon SCADA externo a una vista mimic consumible desde la suite Lechuza.

## Responsabilidades

- Consultar el catalogo de tags del daemon externo configurado por `SCADA_DAEMON_BASE_URL`.
- Mantener un cache de estado por tag y agrupar elementos por estacion/prefijo.
- Exponer endpoints HTTP para catalogo, estado y refresh manual.
- Servir el frontend ubicado en `frontend/` desde el mismo proceso HTTP.

## Endpoints

- `GET /health`
- `GET /api/mimic/elements`
- `GET /api/mimic/state`
- `POST /api/mimic/refresh`

## Configuracion

Variables obligatorias:

- `SCADA_DAEMON_BASE_URL`
- `CITEC_ADAPTER_QUERY_INTERVAL_SECONDS`
- `CITEC_REFRESH_ON_START`
- `CITEC_TAG_REFRESH_INTERVAL_SECONDS`
- `SCADA_CITEC_SERVICE_PORT`
- `SCADA_STATIC_CACHE_SECONDS`

## Integracion en el mono-repo

- El backend vive en `backend/` y el frontend en `frontend/`.
- Se construye desde la raiz de `lechuza-server` y reutiliza `shared/` dentro de la imagen.
- No persiste estado en `volumes/`; el cache vive en memoria.
- El daemon SCADA queda fuera de este repositorio y se consume unicamente por HTTP.
