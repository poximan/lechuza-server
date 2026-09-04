# lechuza-server

Stack operativo desplegado por `docker-compose.yml` bajo el proyecto Compose
`lechu` y la red privada `lechu-backend-net`.

| Servicio | Responsabilidad principal |
| --- | --- |
| `lechu` | Interfaz web y composición de vistas |
| `modbus-collector-service` | GRD, generadores y relés MiCOM |
| `pve-service` | Estado e historial Proxmox |
| `charito-service` | Estado consolidado de `charo-daemon` |
| `modem-link-monitor` | Estado del enlace del módem |
| `alarmero-service` | Alarmas, deduplicación, tiempos, historia y envíos |
| `mensagelo` | Cola durable y entrega SMTP |

Las imágenes y contenedores usan el prefijo `lechu-`, salvo el componente central
`lechu`, cuyo nombre fue fijado explícitamente. La frontera HTTP pertenece a
`platform/edge-platform`; este Compose consume `servicoop-edge-net` como red
externa.

## Alarmas

Los servicios expertos exponen catálogo y flancos mediante su ruta base:

- `GET /api/v1/alarms/catalog`
- `GET /api/v1/alarms/events`
- `POST /api/v1/alarms/events/ack`

Alarmero consulta la lista explícita `ALARMERO_SOURCES_JSON`. Persiste primero cada
flanco, confirma su cursor después, aplica los tiempos del catálogo y recién entonces
genera un despacho recuperable. También administra los checks de correo de inicio y
fin. Mensagelo recibe el pedido idempotente y realiza la entrega SMTP.

El colector publica dos generadores independientes porque tienen temporizaciones
distintas: `/exemys-alarm-generator` y `/generator-alarm-generator`. Los demás
servicios publican el contrato desde su raíz HTTP.

Tiempos vigentes:

- conectividad global roja, GRD individual, módem, Proxmox y Charito: 20 minutos;
- grupo electrógeno en marcha: 60 segundos;
- finalización de cualquier alarma: 20 segundos.

Una alarma individual de GRD sólo existe fuera de la zona roja global. RL1 no forma
parte del catálogo actual.

## Persistencia

Cada servicio usa exclusivamente su volumen. No se comparten bases ni archivos entre
contenedores. `modbus-collector-service` conserva catálogo e historia GRD y una sola
falla/perturbación vigente por relé. Alarmero usa un esquema nuevo sin migraciones en
caliente; una base existente con otro contrato detiene el servicio.

`modbus-collector-service/tools/rebuild_operational_snapshot.py` crea una base nueva y
copia únicamente el catálogo/historia GRD, el estado vigente y la última falla y
perturbación MiCOM.

## Contratos

- HTTP público: `/lechu/`, `/alarmero/`, `/api/`, `/pve/` y `/router/` según
  `platform/edge-platform/edge-gateway/config/routes.txt`.
- MQTT: namespace `lechu/v1/...`.
- Variables: `.env` y `.env.example` declaran el mismo conjunto de claves.
- Puertos TCP: [`../../../ports.txt`](../../../ports.txt) es la fuente única del
  espacio de trabajo; este Compose no mantiene una tabla paralela.

`panelito` queda temporalmente fuera de contrato hasta adaptar sus tópicos al nuevo
namespace.
