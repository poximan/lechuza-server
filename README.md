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
| `scada-citec-service` | Adaptacion del daemon SCADA para mimic | HTTP |

`panelito` y `charo-daemon` son productos externos. Los consumidores usan los contratos HTTP/MQTT; no acceden a bases ni archivos internos de otros servicios.

## Exposicion publica

La frontera HTTP pertenece a `servicoop/platform/edge-platform`. El DNS externo de `comunicaciones.servicoop.com.ar` apunta al router frontera, que reenvia `80/443` al host Docker. `edge-gateway` selecciona los servicios de Lechuza por ruta.

Los servicios publicables se conectan a `servicoop-edge-net`. Esta red pertenece a `edge-platform`; este Compose solo la consume como `external: true`. Desplegar primero `edge-platform` y no crear la red manualmente.

## Integraciones

- `panelexemys` consume las APIs internas de los demas servicios.
- `modbus-collector-service`, `pve-service` y `modem-link-monitor` publican estado por MQTT.
- `charito-service` consulta `/metrics` de las instancias declaradas en `CHARITO_TARGETS_JSON` y publica el consolidado para `panelito`.
- `scada-citec-service` consume `SCADA_DAEMON_BASE_URL`.
- La persistencia local vive bajo `volumes/`.

## Configuracion

Copiar `.env.example` como `.env` y completar secretos, usuarios y endpoints. `.env` y `volumes/` no se versionan. Cada servicio documenta sus endpoints y variables en su propio README.
