# lechuza-server

Despliegue operativo `lechu` definido en `docker-compose.yml`. La frontera HTTP
pertenece a `platform`; este Compose consume `servicoop-edge-net` y crea
`lechu-backend-net`.

## Servicios

| Servicio | Responsabilidad | Puerto publicado |
|---|---|---:|
| `lechu` | UI/API y composición de vistas | `127.0.0.1:8052` |
| `modbus-transport-service` | Cola FIFO y único dueño de los sockets Modbus/TCP | `127.0.0.1:8084` |
| `grd-collector-service` | Estado e histórico de conexiones GRD | `127.0.0.1:8087` |
| `generator-collector-service` | Grupos electrógenos Estivariz y Fontana | `127.0.0.1:8088` |
| `micom-collector-service` | Fallas y perturbaciones de relés MiCOM | `127.0.0.1:8089` |
| `janitza-collector-service` | Magnitudes de analizadores Janitza UMG96S | `127.0.0.1:8095` |
| `pve-service` | Estado e histórico Proxmox | `127.0.0.1:8083` |
| `charito-service` | Estado consolidado de `charo-daemon` | interno |
| `modem-link-monitor` | Estado del enlace del módem | `127.0.0.1:8086` |
| `alarmero-service` | Ciclo de vida y despacho de alarmas | `127.0.0.1:8094` |
| `mensagelo` | Cola durable y entrega SMTP | interno |

Las imágenes y contenedores usan `lechu-*`, excepto `lechu`. Cada servicio corre
sin privilegios y usa exclusivamente su volumen propio.

## Interfaces

Rutas públicas declaradas en `platform/edge-platform/edge-gateway/config/routes.txt`:

```text
/lechu/       UI y API de operación
/alarmero/    UI protegida de alarmas
/api/grd/     contrato GRD
/api/ge/      contrato de grupos electrógenos
/api/reles/   contrato MiCOM
/api/analizadores/ contrato Janitza
/pve/         contrato HTTP de Proxmox
/router/      compatibilidad del monitor de módem
```

El MQTT usa únicamente `lechu/v1/...`:

```text
lechu/v1/{modem,exemys,email,proxmox,services, charito}/...
lechu/v1/rpc/request/{action}
lechu/v1/rpc/response/{client_id}/{corr}
```

Los estados operativos se publican retenidos. Los clientes no acceden a bases ni
archivos de otros servicios.

## Alarmas

Cada generador experto expone:

```text
GET  /api/v1/alarms/catalog
GET  /api/v1/alarms/events
POST /api/v1/alarms/events/ack
```

Alarmero descubre fuentes mediante la lista explícita `ALARMERO_SOURCES_JSON`,
persiste primero el flanco, confirma el cursor después, deduplica y administra el
ciclo completo. El envío opcional de inicio/fin se configura por alarma y siempre
usa los dos destinatarios de `ALARM_RECIPIENTS` mediante Mensagelo.

Tiempos actuales:

- conectividad global roja, GRD individual, módem, Proxmox y Charito: `20 min`;
- grupo electrógeno en marcha: `60 s`;
- confirmación de recuperación: `20 s`.

La alarma individual de GRD no existe dentro de la zona roja global. RL1 aún no
forma parte del catálogo.

## Modbus y MiCOM

`modbus-transport-service` mantiene una cola FIFO por endpoint físico para GRD,
MiCOM, Janitza y GE Estivariz; GE Fontana usa su propio endpoint. Solo hay una
consulta en vuelo por endpoint, incluidos sus reintentos. Los colectores de dominio
no abren sockets Modbus y el transporte es de lectura exclusiva.

El código Modbus está agrupado en `modbus/`: el transporte compartido vive en
`modbus/modbus-transport-service/` y los cuatro colectores especializados en
`modbus/colectores/`. Los nombres de servicio de Compose y los volúmenes de datos
se mantienen estables.

La migración heredada está cerrada. GRD es dueño exclusivo de `grdconectados.db`
y MiCOM de `micom.db`; cada servicio crea una base vacía cuando falta y valida
versión, tablas, columnas, claves e integridad antes de iniciar. GRD conserva
íntegros `grd`, `historicos` y `grd_estado_actual`, mientras MiCOM conserva su
catálogo, fallas y perturbaciones. Las capturas se separan de `fallas_reles` en
`osciloperturbogramas_reles`; `actualizacion_registros_reles` guarda vencimiento y
errores de descarga. Se conservan los registros disponibles en el relé (hasta
cinco), con UTC explícito para evento y descarga. Solo la pantalla convierte a
UTC−3.

Para MiCOM:

- `0x0135` define formato privado o IEC 870 y se lee una vez por sesión;
- al vencer 30 días desde la descarga completa se reconocen las 25 posiciones `0x3700..0x3718`
  (`14080..14104` decimal), leyendo sus 15 palabras porque la ventana indirecta
  rechaza longitudes menores;
- el bloque ya leído de la falla con mayor número se reutiliza y no se repite;
- cada página de perturbación `0x09..0x21` se normaliza a 250 palabras lógicas,
  en dos tramas de 125; `0x2200` se solicita con 9 palabras;
- las cuatro corrientes se guardan crudas; el cálculo de amperes se realiza en la
  presentación con las relaciones del relé;
- se descargan todas las perturbaciones disponibles, sin asociarlas por cercanía a
  una falla. El usuario selecciona la TS del evento en pantalla;
- el vencimiento sobrevive a reinicios. Las descargas incompletas se reintentan
  después de cinco minutos y reutilizan capturas completas vigentes;
- `services/relay_monitoring.py` coordina el ciclo; `relay_metadata.py` mantiene
  parámetros; `relay_query_diagnostics.py` agrega diagnósticos; el lector MiCOM
  traduce el protocolo y el servicio de transporte serializa el canal.

Los Janitza UMG96S con IDs 8, 9 y 10 se consultan secuencialmente mediante función
03. Se leen tensiones y corrientes desde el offset 200 y potencias totales activa,
reactiva y aparente desde el offset 279. Las relaciones TC/TP se leen una sola vez
desde los registros 600..603, se validan, se persisten por equipo y luego se usan
sin política de actualización. El último valor válido se conserva en un archivo
JSON atómico y todas las estampas se guardan en UTC.


APIs principales:

```text
GET  /health
GET  /api/grd/summary
GET  /api/grd/history?grd_id={id}
GET  /api/grd/outages?grd_id={id}
GET  /api/reles/faults
GET  /api/reles/{id_modbus}/disturbances
GET  /api/reles/{id_modbus}/disturbances/{registro}
GET  /internal/v1/modbus/channels
GET  /api/ge/{edificio}/status
GET  /api/analizadores
GET  /api/v1/alarms/catalog
GET  /api/v1/alarms/events
POST /api/v1/alarms/events/ack
POST /api/reles/{id_modbus}/clock-snapshot
GET  /api/reles/observer
POST /api/reles/observer
```

## Persistencia y correo

Los volúmenes son `./volumes/{servicio}`. `mensagelo` persiste solicitudes antes de
responder `202`, exige `Idempotency-Key` en `/send_async` y evita reintentos SMTP
ambiguos. `lechu` muestra ese historial durable y expone por RPC
`get_email_events` los últimos despachos para clientes como Panelito; no expone
cuerpo ni destinatarios por MQTT.

## Configuración

`.env.example` es la plantilla completa de `.env`. Las claves obligatorias deben
estar presentes y no vacías. Los secretos, bases y logs runtime quedan fuera de
git. El despliegue requiere que `platform` haya creado previamente
`servicoop-edge-net`.
