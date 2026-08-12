# modbus-collector-service

Observa equipos mediante Modbus TCP, persiste transiciones en SQLite y publica estados por HTTP y MQTT.

## Responsabilidades

- Mantiene una conexión serializada por gateway Modbus físico.
- Registra histórico y estado GRD vigente en una única transacción.
- Diferencia una lectura no disponible de una desconexión confirmada.
- Supervisa y reinicia los observadores; `/health` informa base, hilos, drivers y MQTT.
- Expone REST (`/api/grd/*`, `/api/reles/*`, `/api/ge/*`) y publica snapshots MQTT.

## Esquema nuevo

El runtime no crea ni modifica tablas. Antes de iniciar debe existir una base `grdconectados.db` con versión de esquema `2`.

El DDL está en `src/persistencia/ddl_esquema.py` y crea únicamente:

- `grd`;
- `historicos`;
- `grd_estado_actual`;
- `reles`;
- `fallas_reles`.

`historicos` usa `PRIMARY KEY (id_grd, timestamp) WITHOUT ROWID`. Esa es la única estructura de acceso agregada para el problema de I/O: ordena físicamente la tabla según todas sus consultas críticas. No se crean índices especulativos. Las restricciones `PRIMARY KEY` y `UNIQUE` de las demás tablas pertenecen a su contrato de identidad.

`mensajes_enviados` no forma parte del esquema del colector. Actualmente pertenece a `mensagelo`/`panelexemys`.

El DDL se niega a sobrescribir archivos existentes. El catálogo y los datos operativos se aprovisionan junto con la base del volumen; el servicio rechaza una base vacía o con un contrato diferente.

## Retención histórica

La política temporal es una decisión operativa y no se inventa en el runtime. El DML de retención conserva un evento ancla por GRD y, sin `--apply`, solo informa candidatos:

```sh
docker compose run --rm --no-deps modbus-collector-service \
  python -m src.persistencia.dml_retencion_historicos \
  --before 2024-01-01T00:00:00Z
```

Para confirmar el borrado se repite el comando agregando `--apply`.

## Variables relevantes

- `MODBUS_COLLECTOR_MW_EXEMYS_MB_*`: conexión, cantidad de registros e intervalo GRD.
- `MODBUS_COLLECTOR_GRD_FAILURE_THRESHOLD`: fallos consecutivos requeridos antes de confirmar desconexión.
- `MODBUS_RELAY_LATEST_FAULT_ADDRESS=14080`: dirección `0x3700` del bloque de última falla MiCOM.
- `MODBUS_RELAY_FAULT_REGISTER_COUNT=15`: tamaño contractual del bloque MiCOM.
- `MODBUS_COLLECTOR_EDIF_FONTANA_MB_*` y `EDIF_*_GE_*`: generadores.
- `MODBUS_COLLECTOR_DATA_DIR`, `MODBUS_COLLECTOR_DATABASE_NAME` y `MODBUS_HISTORY_PAGE_SIZE`.
- `MQTT_PUBLISH_TIMEOUT_SECONDS` y variables `MQTT_*` compartidas.

## Endpoints

- `GET /health`
- `GET /api/grd/descriptions`
- `GET /api/grd/summary`
- `GET /api/grd/history?grd_id=...`
- `GET /api/grd/outages?grd_id=...`
- `GET /api/reles/faults`
- `GET/POST /api/reles/observer`
- `GET /api/ge/edif-estivariz/status`
- `GET /api/ge/edif-fontana/status`
- `GET /api/ge/status`, alias compatible de Estivariz

`/api/grd/summary` consulta `grd_estado_actual`, no recorre `historicos`. Además de los campos compatibles, entrega `unavailable` y `summary.no_disponibles`.

## Mapa de capacidades

| Capacidad | API | Negocio/servicio | Persistencia/adaptador |
|---|---|---|---|
| GRD | `src/api/grd_api.py` | `src/services/grd_service.py`; `src/modbus/server_mb_middleware.py` | `dao_estado_grd.py`, `dao_historicos.py`, `dao_grd.py` |
| Generadores | `src/api/generator_api.py` | `services/generator_state.py` | `server_ge_estivariz.py`, `server_ge_fontana.py` |
| Relés | `src/api/relay_api.py` | `server_mb_reles.py`, `services/state_store.py` | `dao_reles.py`, `dao_fallas_reles.py` |
| Operación | `src/app.py` | `services/orchestrator.py` | `modbus_driver.py`, `mqtt_publisher.py` |

`src/app.py` solo compone el proceso. El volumen operativo es `./volumes/modbus-collector-service:/app/data`; los demás servicios consumen HTTP/MQTT y no acceden a esta base.
