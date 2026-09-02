# modbus-collector-service

Observa equipos mediante Modbus TCP, persiste transiciones en SQLite y publica estados por HTTP y MQTT.

## Responsabilidades

- Mantiene cuatro conexiones TCP independientes: MW/GRD, relés MiCOM,
  GE Estivariz y GE Fontana.
- Registra histórico y estado GRD vigente en una única transacción.
- Diferencia una lectura no disponible de una desconexión confirmada.
- Supervisa y reinicia los observadores; `/health` informa base, hilos, drivers y MQTT.
- Expone REST (`/api/grd/*`, `/api/reles/*`, `/api/ge/*`) y publica snapshots MQTT.
- El transporte Modbus es exclusivamente de lectura: el driver no expone comandos
  de escritura de registros ni bobinas.
- Cada lectura admite tres intentos totales. MW/GRD y ambos grupos electrógenos esperan
  hasta 10 segundos por operación TCP; los relés MiCOM también esperan hasta 10.
- Los tres canales dirigidos al MW Exemys no se bloquean entre sí dentro de la
  aplicación. El gateway conserva la potestad de serializar su medio físico.

## Esquema nuevo

El runtime no crea ni modifica tablas. Antes de iniciar debe existir una base `grdconectados.db` con versión de esquema `7`.

El DDL está en `src/persistencia/ddl_esquema.py` y crea únicamente:

- `grd`;
- `historicos`;
- `grd_estado_actual`;
- `reles`;
- `fallas_reles`.

`historicos` usa `PRIMARY KEY (id_grd, timestamp) WITHOUT ROWID`. Esa es la única estructura de acceso agregada para el problema de I/O: ordena físicamente la tabla según todas sus consultas críticas. No se crean índices especulativos. Las restricciones `PRIMARY KEY` y `UNIQUE` de las demás tablas pertenecen a su contrato de identidad.

`mensajes_enviados` no forma parte del esquema del colector. Actualmente pertenece a `mensagelo`/`panelexemys`.

El DDL se niega a sobrescribir archivos existentes. El catálogo y los datos operativos se aprovisionan junto con la base del volumen; el servicio rechaza una base vacía o con un contrato diferente.

## Relés MiCOM

Cada relé declara en `0x0135` si sus fallas usan fecha privada MiCOM o IEC 870.
Ese dato se lee una vez al encender el observador, se mantiene en memoria y solo
se reintenta si no pudo obtenerse. La fecha privada usa dos palabras para los
segundos transcurridos desde `1994-01-01T00:00:00Z` y dos para los milisegundos;
la fecha IEC 870 usa sus cuatro palabras empaquetadas. Ninguna recibe corrección
horaria. Una vez por hora y por relé se reconocen los 25 registros de fallas
(`0x3700` a `0x3718`). El relé rechaza con excepción Modbus 3 la lectura parcial
de una palabra, por lo que se solicitan las 15 palabras de cada posición y se
conserva la que tenga el mayor número de falla. Si la ráfaga no se completa, se
reintenta en el siguiente ciclo; después
de una lectura completa no se vuelve a consultar la página `37h` hasta la próxima hora. Las cuatro
muestras de corriente se guardan crudas en SQLite y el timestamp conserva tres
decimales junto con el formato que se usó para decodificarlo. Panelexemys presenta
esa estampa tal como la entrega el relé, sin desplazamiento horario. Al pasar el observador de OFF
a ON se leen una sola vez las relaciones internas y los TC primarios de cada
relé. Los valores cargados se
mantienen en memoria durante toda esa sesión. Si falla un bloque, se conserva lo
que ya fue leído y se reintenta únicamente el bloque ausente. Panelexemys recibe
las muestras y la escala por HTTP y calcula los amperes exclusivamente para
presentarlos. El formato temporal, la identificación, las relaciones de TC y la
frecuencia nominal se persisten en `reles`: al reiniciar se presentan los últimos
valores válidos y una lectura posterior los reemplaza primero en SQLite y después
en memoria.

`fallas_reles` conserva una sola fila por relé. Una falla con número mayor
reemplaza en esa misma fila el número, la estampa y las cuatro corrientes; no se
mantiene un histórico de fallas. La última perturbación válida permanece visible
y persistida mientras se intenta recuperar la correspondiente a la falla nueva.
Solo una perturbación verificada contra la falla vigente reemplaza la anterior.

El contrato de fallas incluye el estado de la ronda del observador, el instante
UTC de la próxima encuesta y las cuatro consultas Modbus más recientes de cada
relé. Cada consulta informa dirección, palabras solicitadas y recibidas, estado,
duración y timestamp UTC; esta telemetría es memoria operativa y no se persiste.

El osciloperturbograma se lee del registrador del MiCOM y se persiste junto con la
falla actual. Reiniciar el servicio, apagar el observador o una falla HTTP no borra
la última captura válida.
`0x3D00` se trata como el directorio documentado de perturbaciones: sus entradas
van desde la más antigua hasta la más reciente y cada una informa el número real
de registro. Las páginas `0x38` a `0x3C` seleccionan respectivamente esos cinco
registros y el canal pedido; no contienen por sí mismas la forma de onda. Primero
se elige la entrada cuyo origen y fecha pueden corresponder a la falla vigente;
recién entonces se descargan sus canales. La ventana se obtiene de las cantidades de
muestras de pretiempo y post-tiempo informadas por la cabecera; la aplicación no
cambia esa configuración. Como el directorio no informa el número de falla, la
correspondencia se valida comparando la estampa de la falla con la fecha final de
la captura menos su post-tiempo. El directorio y las muestras se consultan dentro
del reconocimiento horario, no en el ciclo general de un minuto.
Para las formas de onda se usan las relaciones incluidas en la cabecera del propio
registro y la escala documentada
`muestra con signo × TC primario / relación interna × √2`.

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
- `MODBUS_COLLECTOR_MW_EXEMYS_MB_TIMEOUT_SECONDS=10`: timeout de MW/GRD.
- `MODBUS_COLLECTOR_RELAY_MB_TIMEOUT_SECONDS=10`: timeout de relés MiCOM.
- `MODBUS_COLLECTOR_GE_MB_TIMEOUT_SECONDS=10`: timeout de ambos grupos electrógenos.
- `MODBUS_COLLECTOR_MB_READ_ATTEMPTS=3`: intentos totales por lectura para los cuatro conjuntos;
  el driver desactiva los reintentos internos de PyModbus para que no se multipliquen.
- `MODBUS_COLLECTOR_GRD_FAILURE_THRESHOLD`: fallos consecutivos requeridos antes de confirmar desconexión.
- `MODBUS_RELAY_LATEST_FAULT_ADDRESS=14080`: comienzo `0x3700` de los 25 registros de fallas MiCOM.
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
- `GET /api/reles/{id_modbus}/latest-disturbance`
- `POST /api/reles/{id_modbus}/clock-snapshot`, lectura bajo demanda de
  `0x0800–0x0803` usando el formato `0x0135` previamente conocido.
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
| Relés | `src/api/relay_api.py` | `server_mb_reles.py`, `modelo/rele_micom.py`, `services/state_store.py` | `micom_relay_reader.py`, `dao_reles.py`, `dao_fallas_reles.py` |
| Operación | `src/app.py` | `services/orchestrator.py` | `modbus_driver.py`, `mqtt_publisher.py` |

`src/app.py` solo compone el proceso. El volumen operativo es `./volumes/modbus-collector-service:/app/data`; los demás servicios consumen HTTP/MQTT y no acceden a esta base.
