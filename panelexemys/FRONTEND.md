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

## Responsabilidades

- `frontend/src`: presentacion, navegacion y acciones iniciadas por el usuario.
- `src/web/react_api.py`: traduccion de servicios internos a contratos HTTP.
- `src/web/navigation.py`: rutas visibles y autorizacion de navegacion.
- `src/web/clients`: clientes HTTP de los servicios propietarios de cada dato.
- `src/alarmas` y `src/servicios`: reglas operativas ajenas a la presentacion.

Los modulos bajo `src/web/clients` son los adaptadores HTTP consumidos por Flask;
no contienen presentacion ni estado operativo propio.
