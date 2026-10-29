# i20api-service

Importa mediciones de GWF (i2O) mediante OAuth2 Client Credentials
y consultas GraphQL `measuredAt`. No modifica dispositivos ni datos del proveedor.

## Configuración

`config/settings.json` selecciona ubicaciones por ID estable, nombres de presentación,
resolución (`PT15M` inicialmente), retención en meses calendario, horario y demoras de
reintento. Cambiar configuración requiere recrear el servicio. Los streams consultados
son caudal, volumen de caudal y voltajes de batería/externo; se conservan las unidades
devueltas por la API. No se deriva caudal neto ni se inventan valores para canales ausentes.

Copiar `config/gwf.env.example` a `config/gwf.env`, completar credenciales y
dar permiso `0600`. Este archivo está excluido de Git y del contexto de build y se monta
en solo lectura. El proceso y el directorio de datos usan UID/GID 1000.

## Contrato de la API del proveedor

Se utilizan las URL de `gwf.i2owater.com` indicadas en el aviso de migración del
proveedor; el dominio anterior se descontinúa el 1 de noviembre de 2026:

| Uso | URL |
| --- | --- |
| Autorización OAuth2 | `https://auth.api.gwf.i2owater.com/oauth2/token` |
| Scope de lectura | `https://inet.api.gwf.i2owater.com/read` |
| Endpoint GraphQL | `https://inet.api.gwf.i2owater.com/graphql` |

Según el aviso, las credenciales, las estructuras de solicitud/respuesta y el uso
de cursores se mantienen. Después de actualizar el código, se debe reconstruir
la imagen y recrear `i20api-service` para aplicar los cambios. La presentación de
GWF requiere actualizar también Lechu. Esto describe el despliegue; no lo ejecuta.

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
esas lecturas y los cambios de ventana no consultan GWF. No se consulta GWF
al arrancar antes del horario diario, salvo que se pulse el botón manual.

Cada descarga pagina todo el rango retenido de dos meses, incluyendo mediciones
antiguas reportadas con retraso. Se persiste solamente después de obtener todas las
páginas válidas. La identidad `(datapoint id, resolution)` deduplica registros;
un valor cero o igual al anterior sigue siendo válido. HTTP 200 con errores GraphQL
se informa como error, separado de una consulta correcta sin novedades.

SQLite pertenece exclusivamente a este servicio. Se borran las mediciones anteriores
a dos meses calendario, con ajuste del día para meses cortos, incluso si GWF falla.
La tarea local y las lecturas aplican el límite; no hay archivo de histórico adicional.

## Interfaces internas

- `GET /health`: disponibilidad del servicio y estado de sincronización.
- `GET /api/caudalimetros`: equipos, límites retenidos y estado persistido.
- `GET /api/measurements?location_id=...&start=...&end=...`: series locales, fechas ISO UTC.
- `POST /api/sync`: solicita sincronización, devuelve 202 o 409 si hay otra en curso.

Compose no publica este servicio. Lechu compone las rutas `/lechu/api/caudalimetros`,
`/lechu/api/caudalimetros/measurements` y `/lechu/api/caudalimetros/sync`.
La pestaña `/lechu/caudalimetros/` aparece en los modos `secure` y `protected` existentes.

## Revisión del contrato

Las tres URL se declaran una sola vez en `i20api/gwf.py`. El flujo coincide con el
PowerShell de referencia:

- Token mediante `POST`, cuerpo `application/x-www-form-urlencoded`,
  `grant_type=client_credentials`, `client_id`, `client_secret` y el scope de lectura
  exacto de la tabla. `expires_in` está expresado en segundos. Se exige un token
  Bearer válido y se renueva con 60 segundos de margen.
- GraphQL mediante `POST`, cuerpo JSON con `query` y `variables`, y cabecera
  `Authorization: Bearer ...`. Un HTTP 401 renueva el token y repite esa página
  una sola vez; HTTP 200 con `errors` también es un fallo.
- `locationTimeSeries.measuredAt` usa `MeasuredAtFilterInput`, con `when.start` y
  `when.end` en UTC ISO 8601 con milisegundos, `resolution`, `locations.id` y
  `dataStreams.id`. La selección de campos incluye el cursor, identificación,
  ubicación, canal, unidad, fecha, resolución, valor y estadísticas.
- La respuesta real utiliza `pt15m` y `raw` en minúsculas. El adaptador normaliza
  esa etiqueta a `PT15M` y `RAW` antes de validar y persistir; una resolución
  diferente de la solicitada sigue siendo un error. Así, la clave SQLite y las
  consultas del histórico usan la misma forma canónica que la configuración.
- `first` no supera 5000. Se sigue `pageInfo.endCursor` cuando `hasNextPage` es
  verdadero y se rechazan cursores vacíos o repetidos. El cursor pertenece a esa
  descarga: no se reutiliza entre rangos ni sincronizaciones.

El servicio consulta todos los canales configurados en código para el rango retenido;
el PowerShell permite elegir uno y propone 24 horas. Ambos usan el mismo contrato.
La referencia admite listas de canales y muestra un rango de dos meses; esa diferencia
de alcance no demuestra por sí sola la causa de un error del proveedor.

La comprobación HTTP independiente del 29 de octubre de 2026 autenticó correctamente
y recuperó mediciones de LogAluar. La consulta PT15M de 24 horas de `flow-rate`
devolvió cinco registros; el rango de dos meses y cuatro canales devolvió 12.972
registros en tres páginas: 5.765 de caudal, 5.765 de volumen y 1.442 de batería.
No se recibieron registros de voltaje externo. La consulta RAW de 24 horas también
devolvió cinco registros. La comparación estricta de mayúsculas/minúsculas era un
rechazo local de respuestas válidas, independiente del `ServerError` de las pruebas
históricas. Estas comprobaciones consultaron el proveedor sin ejecutar el servicio
ni escribir su base de datos.

Los errores de sincronización conservan el tipo, mensaje y ruta GraphQL enviados por
GWF, con credenciales y token ocultos. Los fallos HTTP, JSON y conectividad se
informan por separado; una respuesta errónea no se interpreta como serie vacía.
Los resultados de pruebas históricas no describen la disponibilidad actual de GWF.
La comprobación de disponibilidad y de mediciones reales requiere una consulta en
vivo, independiente de la revisión estática del contrato.

Documentación de referencia del proveedor en `documentacion/`, en la raíz del
workspace: referencia GraphQL de enero de 2024 (autenticación y tipos, especialmente
páginas 1–2, 6–8 y 11–18), guía de consulta por recepción y guía de extracción de
mayo de 2023. La notificación de migración sustituye únicamente las tres URL.
El servicio utiliza `measuredAt`; el vencimiento de siete días del cursor de
`receivedAt` no aplica a una descarga por rango de fechas.
