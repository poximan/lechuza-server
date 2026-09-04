# alarmero-service

Único responsable del ciclo de vida de alarmas de `lechuza-server`.

## Flujo

1. Consulta por HTTP los catálogos y flancos de `ALARMERO_SOURCES_JSON`.
2. Persiste cada flanco y luego confirma el cursor a la fuente.
3. Aplica activación y recuperación según el generador experto.
4. Deduplica y mantiene incidencias potenciales, activas, en recuperación y resueltas.
5. Crea el despacho en la misma transacción que confirma el flanco.
6. Envía a los dos destinatarios de `ALARM_RECIPIENTS` mediante Mensagelo y sigue su estado.

La UI permite habilitar por alarma el correo de inicio y de fin. También muestra
el estado actual de todo el catálogo, frecuencia móvil de 24 horas, 7, 30 y 365
días, y medianas/P90 de los períodos históricos de actividad e inactividad.

## Persistencia

`backend/db.py` contiene el único esquema SQLite. Si la base no existe se crea; si
existe con otra versión, tablas o columnas, el servicio aborta. No se ejecutan
`ALTER TABLE` ni capas sucesivas de migración.

## API

- `GET /api/incidents`
- `GET /api/dashboard`
- `GET /api/catalog`
- `PUT /api/catalog/{source_id}/{alarm_key}`
- `GET /health`

La vista pública protegida se sirve en `/alarmero/` por `edge-platform`.
