# Frontend de Panelexemys

Panelexemys sirve una aplicacion React y Vite en `/panelexemys/`. Flask conserva las
integraciones operativas, la autorizacion y los contratos JSON consumidos por el
frontend. El contenedor construye React en una etapa Node y copia solamente el
resultado estatico a la imagen Python final.

## Contratos

- La aplicacion React se publica en `/panelexemys/`.
- Los adaptadores JSON de cada pagina viven bajo `/panelexemys/api/`.
- Python conserva integraciones MQTT/HTTP, autorizacion y reglas operativas.
- React presenta datos y solicita acciones; no reproduce reglas de negocio.
- El frontend no guarda estado operativo compartido; lo consulta y lo modifica
  exclusivamente a traves del backend.

La navegacion tiene una fuente unica en `src/web/navigation.py`. El contrato
`GET /panelexemys/api/navigation` informa el modo autenticado y solamente las entradas
visibles para ese modo, ademas del intervalo de actualizacion obligatorio.
En modo seguro se publican solamente Generadores y Reles MiCOM. En modo protegido
se publican todas las vistas, incluidas esas dos. Las lecturas de Reles MiCOM son
seguras; cambiar el estado de su observador sigue siendo una operacion protegida.

## Responsabilidades

- `frontend/src`: presentacion, navegacion y acciones iniciadas por el usuario.
- `src/web/react_api.py`: registro y cableado de rutas HTTP generales.
- `src/web/navigation.py`: rutas visibles y autorizacion de navegacion.
- `src/web/clients`: clientes HTTP de los servicios propietarios de cada dato.
- `src/alarmas` y `src/servicios`: reglas operativas ajenas a la presentacion.

Los modulos bajo `src/web/clients` son los adaptadores HTTP consumidos por Flask;
no contienen presentacion ni estado operativo propio.

Cada vista puede localizarse por nombre en todas las capas que participan.
`frontend/src/pages/PageRenderer.tsx` y `src/web/react_api.py` se limitan al
cableado. Una capa se omite solamente cuando no participa de la capacidad y
agregarla no aportaria claridad operativa.

| Vista | Presentacion | API | Negocio / servicio | DAO / adaptadores |
| --- | --- | --- | --- | --- |
| Overview y detalle GRD | `frontend/src/pages/OverviewPage.tsx` y `OverviewPage.module.css` | `src/web/overview_api.py` | `src/servicios/overview/overview_service.py` | `src/web/clients/modbus_client.py` y `modem_link_monitor_client.py`; no tiene DAO local porque compone fuentes externas |
| Charito | `frontend/src/pages/CharitoPage.tsx` | `src/web/charito_api.py` | `src/servicios/charito/charito_service.py` | `src/web/clients/charito_client.py`; no agrega negocio ni persistencia local |
| Generadores | `frontend/src/pages/GeneratorsPage.tsx` | `src/web/generadores_api.py` | `src/negocio/generadores.py` y `src/servicios/generadores/generadores_service.py` | `src/web/clients/modbus_client.py`; la verdad de los interruptores pertenece al colector Modbus |
| Proxmox | `frontend/src/pages/ProxmoxPage.tsx` | `src/web/proxmox_api.py` | `src/negocio/proxmox.py` y `src/servicios/proxmox/proxmox_service.py` | `src/dao/dao_proxmox_view.py` y `src/web/clients/proxmox_client.py` |
| Reles MiCOM | `frontend/src/pages/RelaysPage.tsx` | `src/web/reles_api.py` | `src/servicios/reles/reles_service.py` | `src/web/clients/modbus_client.py`; no tiene DAO local porque el estado pertenece al colector |
| Mantenimiento | `frontend/src/pages/mantenimiento/MaintenancePage.tsx`, `MaintenanceContract.ts` y `MaintenancePage.module.css` | `src/web/mantenimiento_api.py` | `src/negocio/mantenimiento.py` y `src/servicios/mantenimiento/mantenimiento_service.py` | `src/dao/dao_mantenimiento.py`, `src/dao/mantenimiento_data.json` y `src/assets/topologia.png` |
| Mensagelo | `frontend/src/pages/MensageloPage.tsx` | `src/web/mensagelo_api.py` | `src/servicios/mensagelo/mensagelo_service.py` | `src/dao/dao_mensagelo_attempts.py`; no agrega negocio porque expone un historial ya normalizado |
| Broker | `frontend/src/pages/BrokerPage.tsx` | `src/web/broker_api.py` | `src/servicios/broker/broker_service.py` | `src/servicios/mqtt/mqtt_client_manager.py`; no tiene DAO porque muestra estado vivo del proceso |
| Correo | `frontend/src/pages/EmailPage.tsx` | `src/web/email_api.py` | `src/servicios/email/email_service.py`; no agrega negocio separado porque reporta salud e inicia una operacion existente sin reglas de dominio propias | `src/dao/dao_email_health.py`, `src/servicios/email/mensagelo_client.py` y `src/servicios/mqtt/mqtt_event_bus.py` |

No existe un renderizador generico de objetos JSON: cada pagina valida su contrato y
presenta componentes propios del dominio. Los errores de contrato quedan aislados en
la pagina afectada y se reintentan al recibir el siguiente snapshot.
