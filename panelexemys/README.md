# panelexemys

Aplicacion Dash/Flask que presenta el tablero operativo y orquesta alarmas/mensajeria.

## Componentes

- Frontend Dash (`src/web/*`) con clientes HTTP en `src/web/clients` para Modbus, Proxmox, router, etc.
- Gestor de alarmas (`src/alarmas`) que usa Mensagelo para emails.
- Solapa protegida `mensagelo` con los ultimos diez intentos de envio registrados en memoria del proceso.
- MQTT client para recibir estados (`lechuza-server/*`).

## Endpoints/Servicios

- Servido via Waitress en `:8052`; toda la exposicion hacia afuera pasa por `router-atrevido` mediante la red externa `servicoop-edge-net`.
- No accede directamente a SQLite; toda la informacion proviene de APIs (`MODBUS_MW_API_BASE`, `PVE_API_BASE`, `ROUTER_SERVICE_BASE_URL`).
- Todo el estado mutable propio vive bajo `PANELEXEMYS_DATA_DIR` y, en Docker Compose, queda persistido en `./volumes/panelexemys:/app/data`.
- Los archivos operativos vigentes son `panelexemys.db`, `observar.json`, `charo.json` y `proxmox-observar.json`; no se persiste nada dentro de `src/`.

## Variables principales

Ver `config.py`: URLs base (`MODBUS_MW_API_BASE`, `PVE_API_BASE`, `ROUTER_SERVICE_BASE_URL`), credenciales MQTT (`MQTT_BROKER_*`), destinatarios de alarmas, links del dashboard y hosts del chequeo de correo. Todas deben estar presentes en `.env`.

Los assets estaticos viven en `src/assets` y el javascript auxiliar en `src/assets/nav-toggle.js`.

## Contratos vigentes

- `panelito` consume por MQTT los topicos normalizados `lechuza-server/router/status`, `lechuza-server/modbus/grd/summary`, `lechuza-server/modbus/grd/disconnected`, `lechuza-server/email/status`, `lechuza-server/email/event`, `lechuza-server/pve/status`, `lechuza-server/modbus/ge/status`, `charito/state` y `panelexemys/status`.
- `panelito` dispara pedidos RPC por `lechuza-server/rpc/req/{accion}` y recibe respuestas en `lechuza-server/rpc/res/{clientId}/{corr}`. Las acciones vigentes son `get_global_status`, `get_modem_status` y `send_email_test`.
- `panelexemys` consume por HTTP a `modbus-mw-service`, `pve-service`, `router-telef-service`, `charito-service` y `mensagelo`.
- `charo-daemon` queda fuera de este arbol MQTT legado y sigue un contrato propio normalizado sobre `charodaemon/host/{clientId}/*`.

## Objetivo de migracion

- Separar topicos de estado y topicos de comando.
- Evitar respuestas RPC en topicos de estado compartidos.
- Mover gradualmente el arbol `exemys/*` hacia namespaces funcionales de `lechuza-server/*`.
- El detalle consolidado vive en [docs/contratos-sistema.md](/c:/HSD/git/infra-monitor/docs/contratos-sistema.md).
