# Migracion frontend de Panelexemys

Panelexemys no se reemplaza como una sola pantalla: cada pagina Dash conserva hoy
su layout, callbacks, autorizacion y traduccion de datos. La migracion se realiza
por pagina y elimina en la misma modificacion el responsable Dash sustituido.

## Contratos

- La aplicacion React se publicara en `/dash/` sin cambiar la ruta externa.
- Los adaptadores JSON de cada pagina viviran bajo `/dash/api/`.
- Python conserva integraciones MQTT/HTTP, autorizacion y reglas operativas.
- React presenta datos y solicita acciones; no reproduce reglas de negocio.
- Una pagina no puede mantener simultaneamente callbacks Dash y mutaciones React.

La navegacion ya tiene una fuente unica en `src/web/navigation.py`. El contrato
`GET /dash/api/navigation` informa el modo autenticado y solamente las entradas
visibles para ese modo.

## Orden de sustitucion

1. shell, navegacion y contrato visual compartido;
2. vistas de solo lectura: Charito, generadores y Proxmox;
3. dashboard Exemys y sus graficos/tablas;
4. vistas protegidas: reles MiCOM y mantenimiento;
5. Mensagelo y broker, que contienen operaciones protegidas;
6. eliminacion de Dash, sus assets y dependencias cuando no quede ninguna pagina.

Cada paso debe incorporar contrato duro, validacion estatica y eliminacion de
imports, callbacks, estilos y archivos que hayan quedado sin consumidor.
