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
| `i20api-service` | Histórico de caudalímetros i2O y sincronización GWF | interno |
| `modem-link-monitor` | Estado del enlace del módem | `127.0.0.1:8086` |
| `alarmero-service` | Ciclo de vida y despacho de alarmas | `127.0.0.1:8094` |
| `mensagelo` | Cola durable y entrega SMTP | interno |

Las imágenes y contenedores usan `lechu-*`, excepto `lechu`. Cada servicio corre
sin privilegios. Los volúmenes de datos son exclusivos de cada servicio.

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
lechu/v1/{modem,exemys,email,proxmox,services,charito}/...
lechu/v1/rpc/request/{action}
lechu/v1/rpc/response/{client_id}/{corr}
```

Los estados operativos se publican retenidos. Los clientes no acceden a bases ni
archivos de otros servicios.

La navegación interna de Lechu ocupa una barra vertical a la izquierda, con
iconos y etiquetas del contrato `/lechu/api/navigation`. El backend conserva la
autoridad sobre los nombres, destinos y secciones habilitadas por modo de acceso.
`lechu/frontend/src/components/SectionNavigation.tsx` representa esos enlaces,
marca la sección activa y permite recorrerlos con flechas, Inicio y Fin. En
pantallas estrechas queda una barra de iconos con nombres accesibles y tooltips;
la barra tiene desplazamiento propio cuando supera la altura disponible.

El contenido comienza junto a esa barra. La cabecera global concentra la identidad
del producto y los accesos al menú y al cierre de sesión. Generadores muestra sus
alertas dentro de cada tarjeta. El logo se utiliza en el splash de entrada, el
favicon y el acceso desde el landing; el splash no reaparece al cambiar de sección.

La pantalla Proxmox distingue los discos virtuales configurados y la ocupación
por volumen dentro de cada vhost del almacenamiento general del hipervisor.
El contrato, los requisitos del agente y los permisos están detallados en
[`pve-service/README.md`](pve-service/README.md). No se presentan como 0 % las
mediciones que no pudo devolver QEMU Guest Agent.

## Destino del monitor del router

`modem-link-monitor` toma la IP pública y el puerto exclusivamente de `TARGET_IP`
y `TARGET_PORT` en `.env`, transmitidos por Compose. Al cambiar el destino hay que
recrear ese contenedor para aplicar las nuevas variables. El estado operativo
persistido se descarta si pertenece a otra IP o puerto; el incidente de alarma
conserva su identidad hasta que el nuevo destino confirme recuperación, evitando
un nuevo aviso causado solo por el cambio de dirección.

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

- conectividad global roja, GRD individual, módem, Proxmox y daemon Charito: `20 min`;
- proceso monitoreado por Charito: `10 min`;
- grupo electrógeno en marcha: `60 s`;
- confirmación de recuperación: `20 s`.

El monitor del router usa Globalping como proveedor principal mediante mediciones
`ping` con `protocol=TCP`, el puerto configurado y una conexion por sonda. La
API elige hasta tres sondas distribuidas entre Sudamerica, Norteamerica y Europa.
Se interpreta la cantidad de conexiones TCP establecidas en las estadisticas;
una respuesta ICMP no confirma la disponibilidad del puerto. La primera conexion
exitosa confirma el acceso inmediatamente. El plazo de resultados es 35 segundos,
para que tambien alcance la confirmacion de fallos TCP que llegan con demora.
Si la medicion es inconclusa, se usa Check-Host como respaldo. El proveedor usado
y todos los intentos se muestran en Exemys. `MODEM_EXTERNAL_PROVIDER=check-host`
permite seleccionar explicitamente el proveedor anterior; el valor inicial es
`globalping`. `GLOBALPING_BASE_URL` y `GLOBALPING_RESULT_TIMEOUT_SECONDS`
configuran el nuevo proveedor. Referencia: https://globalping.io/docs/api.globalping.io.

Para el respaldo, el monitor consulta el catalogo oficial de Check-Host y selecciona
tres sondas explicitas, rotando primero las menos usadas y procurando diversidad
de paises y redes. El catalogo se conserva una hora; si falla su actualizacion,
se reutiliza el anterior. Cuando no se obtuvo ningun catalogo, la primera consulta
puede utilizar la seleccion del proveedor.

Cada intento de Check-Host espera resultados asincronos hasta 45 segundos. Una conexion
exitosa declara el puerto abierto inmediatamente; las otras sondas pendientes
se muestran como no esperadas porque la conexion ya esta confirmada. Si el
intento queda inconcluso, se realiza un segundo con otras sondas disponibles.
Las sondas sin resultado o con errores internos (por ejemplo, `Too many open files`)
descansan 15 minutos. Un error de ese tipo nunca confirma una caida del destino.
Una respuesta HTTP 429 detiene el ciclo, evitando reiterar solicitudes limitadas.
Los limites se configuran mediante `CHECK_HOST_MAX_ATTEMPTS`,
`CHECK_HOST_NODE_COOLDOWN_SECONDS`, `CHECK_HOST_NODES_REFRESH_SECONDS` y los
plazos de consulta existentes. El intervalo entre ciclos sigue siendo 300 segundos.

El monitor inicia `modem:link` solo cuando las tres sondas de un mismo intento
informan fallos explicitos de conexion y ese conjunto permanece confirmado
durante al menos 10 segundos desde su primera observacion completa. Las sondas
sin resultado, sus errores internos y una seleccion de menos de tres sondas
nunca confirman el cierre. La vista Exemys muestra cada intento, la identidad de
las sondas y, si el chequeo es inconcluso, la ultima confirmacion con su fecha.
No inicia esa alarma solo por conectividad global roja, ya que Exemys tiene una alarma propia. Una
vez iniciada, el router solo se considera recuperado tras dos chequeos externos
consecutivos abiertos y con el porcentaje GRD fuera de zona roja. Un resultado
desconocido o una consulta GRD fallida conserva el estado anterior y reinicia
la confirmacion de recuperacion. `globalping_probe.py` y `tcp_probe.py` interpretan
los tests externos, `connectivity_client.py` adapta el resumen HTTP GRD y
`alarm_source.py` decide los flancos; Alarmero sigue siendo el unico propietario
del historial.

La misma vista muestra una traza UDP hacia el destino, originada dentro del
contenedor `lechu` por `tracepath`, y una prueba TCP directa desde ese contenedor
al puerto configurado. Se actualizan en segundo plano como maximo una vez cada
cinco minutos y no bloquean la consulta HTTP de Exemys. La secuencia muestra
solo los routers que respondieron; agrupa los saltos sin respuesta en un tramo
no observable. Un tramo gris no indica que el trafico se detuvo alli. La prueba
TCP confirma por separado si `lechu` pudo conectar al destino.

Cada proceso de Charito tiene una alarma propia. Solo una respuesta HTTP exitosa y no
vacía de `/metrics` confirma que su daemon está vivo; un fallo de métricas con esa
respuesta conserva la última condición conocida del proceso. Si el daemon deja de
confirmar disponibilidad, los procesos pasan a condición inactiva y siguen los
tiempos normales de recuperación. Por defecto se envían correos de inicio; las
opciones de inicio y fin se configuran por alarma.

Frecuencia cuenta incidentes confirmados según el comienzo de la caída en ventanas
móviles exactas de 24 horas, 7, 30 y 365 días. Alarmero carga su historial desde
su propia base al iniciar y cada medianoche local; entre recargas incorpora las
confirmaciones en memoria. Si la primera observación registrada de una alarma no
cubre una ventana completa, la pantalla muestra `!?` en lugar de un cero no
verificado.

El mapa de fuentes de estas capacidades es: `charito-service/src/poller.py` adapta
`/metrics`, `charito-service/src/process_alarm_service.py` decide las alarmas de
procesos, `alarmero-service/backend/frequency_repository.py` consulta el historial
propio de Alarmero, `alarmero-service/backend/frequency_service.py` conserva la
proyección diaria en memoria y `alarmero-service/frontend/src/components/` presenta
las frecuencias y la configuración de avisos.

No se inicia una alarma individual de GRD mientras la conectividad global está
en zona roja. Si un GRD ya estaba en alarma, su incidente se conserva hasta una
lectura válida de recuperación. Tampoco se cierra por un fallo temporal de lectura;
una caída continua genera un solo aviso de inicio. RL1 aún no forma parte del
catálogo.

## Modbus y MiCOM

`modbus-transport-service` mantiene una cola FIFO por endpoint físico para GRD,
MiCOM, Janitza y GE Estivariz; GE Fontana usa su propio endpoint. Solo hay una
consulta en vuelo por endpoint, incluidos sus reintentos. Los colectores de dominio
no abren sockets Modbus y el transporte es de lectura exclusiva.

En todos los GRD activos se usa el mismo criterio: el bit `0` de la palabra de
estado indica conexión cuando vale `1` y caída cuando vale `0`. Un fallo de lectura
deja el estado actual como desconocido y conserva el último valor confirmado como
referencia. Solo una lectura válida del bit `0` puede iniciar una transición a
desconectado. La lista de desconectados omite los equipos con lectura actualmente
no disponible; sus
incidentes permanecen abiertos hasta confirmar la recuperación. La UI muestra los
fallos de lectura por separado.

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
  con esperas de 30 minutos, 2 horas, 12 horas y luego 24 horas, y reutilizan
  capturas completas vigentes;
- `services/relay_monitoring.py` coordina el ciclo; `relay_metadata.py` mantiene
  parámetros; `relay_query_diagnostics.py` agrega diagnósticos; el lector MiCOM
  traduce el protocolo y el servicio de transporte serializa el canal.

Los Janitza UMG96S con IDs 8, 9 y 10 se consultan secuencialmente mediante función
03. Se leen tensiones y corrientes desde el offset 200 y potencias totales activa,
reactiva y aparente desde el offset 279. Las relaciones TC/TP se leen una sola vez
desde los registros 600..603, se validan, se persisten por equipo y luego se usan
sin política de actualización. El último valor válido se conserva en un archivo
JSON atómico y todas las estampas se guardan en UTC.

La sección Analizadores ofrece el mismo control global «Observar» que MiCOM:
se puede consultar en modo seguro y modificar únicamente en modo protegido.
El primer inicio mantiene la lectura automática activada; cada cambio se persiste
atómicamente en `JANITZA_DATA_DIR/janitza-observer.json`, separado de las mediciones
y relaciones TC/TP de `janitza-state.json`. Un estado persistido inválido impide
iniciar el colector. Al pausar no se envían nuevas consultas; una petición ya en
curso puede finalizar. Se conservan las últimas mediciones, sus fechas y errores.
Al reactivar se retoma en el siguiente ciclo del intervalo configurado.

`src/services/observer_state_store.py` del colector es dueño de ese estado;
`services/collector.py` aplica la pausa entre equipos y lecturas. Lechu delega el
cambio mediante `PUT /lechu/api/analizadores/observer`, con `enabled` booleano y
autorización del lado servidor. La ruta directa `/api/analizadores/observer`
también exige autorización en las reglas del gateway. El cambio requiere
actualizar conjuntamente los fuentes de Janitza, Lechu y las reglas del gateway.


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
GET  /api/analizadores/observer
POST /api/analizadores/observer
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
