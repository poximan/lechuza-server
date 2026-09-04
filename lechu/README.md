# lechu

Aplicación React/Flask que presenta las capacidades de `lechuza-server`. Compone
contratos HTTP y MQTT, pero no decide ni persiste ciclos de alarmas.

## Navegación

- Modo seguro: `generadores` y `relés MiCOM`.
- Modo protegido: todas las vistas, incluidas `exemys`, `correo`, Proxmox,
  mantenimiento, Mensagelo, Broker y Charito.
- Ruta base única: `/lechu/`.

## Responsabilidades

- `frontend/src`: presentación y acciones del operador.
- `src/web`: contratos HTTP de cada vista.
- `src/servicios`: composición de servicios externos.
- `src/negocio`: reglas exclusivas de presentación operativa.
- `src/dao`: estado local propio de las vistas; nunca accede a bases ajenas.

La prueba de correo usa `EMAIL_TEST_RECIPIENTS`; no forma parte del flujo de
alarmas. Alarmero es el único dueño de sus destinatarios, temporización,
persistencia y envío.

Las lecturas MiCOM se presentan desde la persistencia del colector mientras no
llegue un dato mejor. Las corrientes se calculan en el frontend a partir de los
valores crudos y las relaciones informadas por el relé.

El contrato MQTT usa `lechu/v1/...`. `panelito` se adaptará en una etapa posterior.
