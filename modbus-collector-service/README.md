# modbus-collector-service

Observa equipos via Modbus TCP, persiste eventos en SQLite y publica resumenes por HTTP y MQTT.

## Responsabilidades
- Mantiene una capa comun de conexion Modbus TCP (`ModbusTcpDriver`) instanciada por conexion fisica.
- Usa la conexion `mw-exemys` para GRDs, reles MiCOM y el generador de Edificio Estivariz.
- Usa la conexion `edif-fontana` para el generador de Edificio Fontana.
- Expone REST (`/api/grd/*`, `/api/reles/*`, `/api/ge/edif-estivariz/status`, `/api/ge/edif-fontana/status`).
- Publica grado global, GRDs desconectados y estados de generadores en MQTT.

## Variables relevantes
- `MODBUS_COLLECTOR_MW_EXEMYS_MB_HOST`, `MODBUS_COLLECTOR_MW_EXEMYS_MB_PORT`, `MODBUS_COLLECTOR_MW_EXEMYS_MB_ID`, `MODBUS_COLLECTOR_MW_EXEMYS_MB_COUNT`, `MODBUS_COLLECTOR_MW_EXEMYS_MB_INTERVAL_SECONDS`.
- `MODBUS_COLLECTOR_EDIF_FONTANA_MB_HOST`, `MODBUS_COLLECTOR_EDIF_FONTANA_MB_PORT`, `MODBUS_COLLECTOR_EDIF_FONTANA_MB_ID`.
- `EDIF_ESTIVARIZ_GE_*` para mapear el registro/bits del generador Estivariz.
- `EDIF_FONTANA_GE_REGISTER_OFFSET=1046`, `EDIF_FONTANA_GE_REGISTER_COUNT=1`, `EDIF_FONTANA_GE_LINE_BIT_INDEX=0`, `EDIF_FONTANA_GE_GENERATOR_BIT_INDEX=1`, `EDIF_FONTANA_GE_INTERVAL_SECONDS`, `EDIF_FONTANA_GE_TOPIC`.
- `MODBUS_COLLECTOR_DATA_DIR` y `MODBUS_COLLECTOR_DATABASE_NAME`.
- MQTT: mismas credenciales que Panelexemys (`MQTT_BROKER_*`).

## Endpoints
- `GET /health`
- `GET /api/grd/descriptions`, `/api/grd/summary`, `/api/grd/history?grd_id=...`
- `GET /api/reles/faults`, `GET/POST /api/reles/observer`
- `GET /api/ge/edif-estivariz/status`
- `GET /api/ge/edif-fontana/status`
- `GET /api/ge/status` queda como alias compatible de Estivariz.

## Volumenes
El contenedor usa `./volumes/modbus-collector-service:/app/data`. Panelexemys solo consume estas APIs; no accede a la base directamente.
