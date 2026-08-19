# panelexemys

Aplicacion React/Flask que presenta el tablero operativo y orquesta
alarmas/mensajeria. La arquitectura frontend se detalla en `FRONTEND.md`.

## Componentes

- Frontend React y Vite (`frontend/src`) basado en `platform/frontend-foundation`.
- API Flask (`src/web/react_api.py`) y clientes HTTP en `src/web/clients` para Modbus, Proxmox, router, etc.
- Gestor de alarmas (`src/alarmas`) que usa Mensagelo para emails.
- API interna autenticada `GET /internal/alarms` para que Alarmero consuma estados y eventos sin leer la base.
- Solapa protegida `mensagelo` con los ultimos diez intentos de envio registrados en memoria del proceso.
- MQTT client para recibir estados (`lechuza-server/*`).

## Endpoints/Servicios

- Servido via Waitress en `:8052`; toda la exposicion hacia afuera pasa por `edge-platform` mediante la red externa `servicoop-edge-net`.
- No accede directamente a SQLite; toda la informacion proviene de APIs (`MODBUS_COLLECTOR_API_BASE`, `PVE_API_BASE`, `MODEM_LINK_MONITOR_URL`).
- Todo el estado mutable propio vive bajo `PANELEXEMYS_DATA_DIR` y, en Docker Compose, queda persistido en `./volumes/panelexemys:/app/data`.
- Los archivos operativos vigentes son `panelexemys.db`, `observar.json`, `charo.json` y `proxmox-observar.json`; no se persiste nada dentro de `src/`.

## Variables principales

Ver `config.py`: URLs base (`MODBUS_COLLECTOR_API_BASE`, `PVE_API_BASE`, `MODEM_LINK_MONITOR_URL`), credenciales MQTT (`MQTT_BROKER_*`), destinatarios de alarmas, links del panel y hosts del chequeo de correo. Todas deben estar presentes en `.env`. El intervalo del frontend se define mediante `PANELEXEMYS_REFRESH_MS`.

Los assets estaticos de interfaz se generan desde `frontend/src`. Los assets
operativos versionados, como la topologia de Mantenimiento, viven en
`src/assets`, Vite los incorpora de forma explicita y se sirven bajo
`/panelexemys/`.

## Fuentes por pestaña

Cada pestaña tiene presentacion, controlador y servicio localizables por nombre.
Las capas de negocio, DAO o adaptadores se agregan cuando la capacidad realmente
contiene reglas, persistencia o integraciones. El mapa completo y las excepciones
estan documentados en `FRONTEND.md`. `src/web/react_api.py` solamente registra
rutas y conecta controladores.

## Contratos vigentes

- `panelito` consume por MQTT los topicos normalizados `lechuza-server/router/status`, `lechuza-server/modbus/grd/summary`, `lechuza-server/modbus/grd/disconnected`, `lechuza-server/email/status`, `lechuza-server/email/event`, `lechuza-server/pve/status`, `lechuza-server/modbus/ge/edif-estivariz/status`, `lechuza-server/modbus/ge/edif-fontana/status`, `charito/state` y `panelexemys/status`.
- `panelito` dispara pedidos RPC por `lechuza-server/rpc/req/{accion}` y recibe respuestas en `lechuza-server/rpc/res/{clientId}/{corr}`. Las acciones vigentes son `get_global_status`, `get_modem_status` y `send_email_test`.
- `panelexemys` consume por HTTP a `modbus-collector-service`, `pve-service`, `modem-link-monitor`, `charito-service` y `mensagelo`; `alarmero-service` consume a `panelexemys` por HTTP.
- El seguimiento Proxmox y sus alarmas usan la misma lista `PVE_VHOST_IDS`; actualmente comprende las VMs `100`, `102`, `107`, `108` y `110`.
- Un snapshot Charito completo y valido tambien permite cerrar, mediante la recuperacion normal, incidencias de instancias retiradas del inventario. Los errores o snapshots invalidos conservan las incidencias existentes.
- `panelexemys` envia email a `ALARM_EMAIL_RECIPIENT` cuando cambia el interruptor lado grupo de Estivariz o Fontana. Mantiene ademas la alarma sostenida historica para Estivariz cuando el lado grupo permanece cerrado.
- `charo-daemon` queda fuera de este arbol MQTT legado y sigue un contrato propio normalizado sobre `charodaemon/host/{clientId}/*`.

`/internal/alarms` no es una pantalla ni una ruta publica para operadores. Es el
contrato HTTP privado con el que `alarmero-service` replica los estados
`potential`, `active`, `recovering` y `resolved` administrados por `panelexemys`.

## Objetivo de migracion

- Separar topicos de estado y topicos de comando.
- Evitar respuestas RPC en topicos de estado compartidos.
- Mover gradualmente el arbol `exemys/*` hacia namespaces funcionales de `lechuza-server/*`.
- El detalle consolidado vive en [`../../docs/contratos-sistema.md`](../../docs/contratos-sistema.md).
