# lechuza-server

Stack operativo de Lechuza desplegado desde `docker-compose.yml`.

| Servicio | Responsabilidad | Interfaces |
| --- | --- | --- |
| `panelexemys` | Dashboard, alarmas y coordinacion | HTTP, MQTT |
| `mensagelo` | Envio y registro de correo | HTTP interno |
| `modbus-collector-service` | Estado GRD, MiCOM y generadores | HTTP, MQTT |
| `pve-service` | Estado e historial de Proxmox | HTTP, MQTT |
| `modem-link-monitor` | Estado del enlace del router | HTTP, MQTT |
| `charito-service` | Estado consolidado de `charo-daemon` | HTTP, MQTT |
| `alarmero-service` | Historial y dashboard de incidencias | HTTP |

`panelito` y `charo-daemon` son productos externos. Los consumidores usan los contratos HTTP/MQTT; no acceden a bases ni archivos internos de otros servicios.

## Exposicion publica

La frontera HTTP pertenece a `servicoop/platform/edge-platform`. El DNS externo de `comunicaciones.servicoop.com.ar` apunta al router frontera, que reenvia `80/443` al host Docker. `edge-gateway` selecciona los servicios de Lechuza por ruta.

Los servicios publicables se conectan a `servicoop-edge-net`. Esta red pertenece a `platform`; este Compose solo la consume como `external: true`. Desplegar primero `platform/docker-compose.yml` y no crear la red manualmente.

La comunicacion privada entre servicios usa la red explicita
`comunic-mon-backend-net`; el despliegue no depende del nombre automatico de
Compose.

## Integraciones

- `panelexemys` consume las APIs internas de los demas servicios.
- `modbus-collector-service`, `pve-service` y `modem-link-monitor` publican estado por MQTT.
- `charito-service` consulta `/metrics` de las instancias declaradas en `CHARITO_TARGETS_JSON` y publica el consolidado para `panelito`.
- `alarmero-service` consume por HTTP el ciclo de alarmas de `panelexemys` y los despachos de `mensagelo`; no accede a sus bases.
- La persistencia local vive bajo `volumes/`.

## Configuracion

Copiar `.env.example` como `.env` y completar secretos, usuarios y endpoints. `.env` y `volumes/` no se versionan. Cada servicio documenta sus endpoints y variables en su propio README.

## Ciclo de alarmas y correo

`panelexemys` es responsable de detectar la condicion, exigir su duracion minima,
mantener la incidencia activa y decidir cuando queda recuperada. La incidencia y su
identificador idempotente se conservan en `panelexemys.db`, incluso ante reinicios.

`mensagelo` es responsable de aceptar una sola vez ese identificador, persistir el
pedido y efectuar un unico intento SMTP. Un HTTP `202` confirma aceptacion durable;
no confirma entrega. Una incidencia solo puede generar otra notificacion despues de
una recuperacion valida sostenida durante `ALARM_MIN_RECOVERY_DURATION_MINUTES`.

`alarmero-service` mantiene una proyeccion append-only propia para consulta. Muestra
alarmas `potential`, `active`, `recovering` y `resolved`, correlaciona destinatarios
y estado SMTP por el identificador de incidencia y calcula frecuencias, mediana y
percentil 90 de despeje. Las estimaciones iniciales se declaran en
`ALARM_CLEARANCE_ESTIMATES_MINUTES`. El acceso publico es protegido en `/alarmero/`.

Snapshots ausentes o invalidos no resuelven alarmas. Para `charito-service`, la
desaparicion temporal de una instancia tampoco se interpreta como recuperacion.
