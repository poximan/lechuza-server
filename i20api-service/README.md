# i20api-service

Importa mediciones de Sentryx Intelligent Network mediante OAuth2 Client Credentials
y consultas GraphQL `measuredAt`. No modifica dispositivos ni datos del proveedor.

## Configuración

`config/settings.json` selecciona ubicaciones por ID estable, nombres de presentación,
resolución (`PT15M` inicialmente), retención en meses calendario, horario y demoras de
reintento. Cambiar configuración requiere recrear el servicio. Los streams consultados
son caudal, volumen de caudal y voltajes de batería/externo; se conservan las unidades
devueltas por la API. No se deriva caudal neto ni se inventan valores para canales ausentes.

Copiar `config/sentryx.env.example` a `config/sentryx.env`, completar credenciales y
dar permiso `0600`. Este archivo está excluido de Git y del contexto de build y se monta
en solo lectura. El proceso y el directorio de datos usan UID/GID 1000.

## Sincronización

El logger comunica a las 00:00 UTC−3. El primer intento comienza a las 00:10.
Si no incorpora registros nuevos o la API falla, reintenta una hora después y,
si vuelve a fallar, dos horas después (habitualmente 01:10 y 03:10). Tras tres
intentos sin novedades queda suspendido hasta el siguiente día. La hora de los
reintentos se calcula desde el inicio del intento anterior. Un reinicio conserva
intentos y suspensión; si un intento fue interrumpido, cuenta como consumido.
El siguiente arranque completa solamente el próximo intento pendiente, sin descargar
repetidamente para compensar un período en que el servicio estuvo apagado.

La sincronización manual corre en segundo plano y no cambia el calendario automático.
Solo una descarga puede estar activa. El frontend consulta estado y series locales;
esas lecturas y los cambios de ventana no consultan Sentryx. No se consulta Sentryx
al arrancar antes del horario diario, salvo que se pulse el botón manual.

Cada descarga pagina todo el rango retenido de dos meses, incluyendo mediciones
antiguas reportadas con retraso. Se persiste solamente después de obtener todas las
páginas válidas. La identidad `(datapoint id, resolution)` deduplica registros;
un valor cero o igual al anterior sigue siendo válido. HTTP 200 con errores GraphQL
se informa como error, separado de una consulta correcta sin novedades.

SQLite pertenece exclusivamente a este servicio. Se borran las mediciones anteriores
a dos meses calendario, con ajuste del día para meses cortos, incluso si Sentryx falla.
La tarea local y las lecturas aplican el límite; no hay archivo de histórico adicional.

## Interfaces internas

- `GET /health`: disponibilidad del servicio y estado de sincronización.
- `GET /api/caudalimetros`: equipos, límites retenidos y estado persistido.
- `GET /api/measurements?location_id=...&start=...&end=...`: series locales, fechas ISO UTC.
- `POST /api/sync`: solicita sincronización, devuelve 202 o 409 si hay otra en curso.

Compose no publica este servicio. Lechu compone las rutas `/lechu/api/caudalimetros`,
`/lechu/api/caudalimetros/measurements` y `/lechu/api/caudalimetros/sync`.
La pestaña `/lechu/caudalimetros/` aparece en los modos `secure` y `protected` existentes.

## Documentación y limitación observada

Implementado a partir de los documentos locales de Sentryx en `documentacino`:
referencia GraphQL de 2024 y guías de recepción/extracción. `receivedAt` requiere
recuperación si su cursor envejece siete días; la consulta por fechas del rango retenido
evita depender de ese cursor para recuperar demoras del logger.

Las pruebas del 7 de octubre de 2026 autenticaron y encontraron LogAluar, pero
`measuredAt` en RAW y PT15M y `receivedAt` devolvieron `ServerError`. El frontend
muestra este error y no presenta mediciones simuladas. El proveedor debe resolver
el acceso a las series para validar datos reales de extremo a extremo.
