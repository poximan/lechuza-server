# wol-service

Servicio dueño del encendido Wake-on-LAN. Construye un paquete mágico de 102
bytes, lo envía por UDP al broadcast configurado y considera que el equipo arrancó
cuando acepta conexiones TCP en el puerto SSH 22.

## Entradas

- MQTT `lechu/v1/wol/request`, usado por Panelito. La respuesta se publica en el
  `reply_to` validado de la solicitud.
- HTTP sobre el socket Unix configurado en `WOL_CONTROL_SOCKET`, usado por la
  solapa Mantenimiento de Lechu.

```text
GET  /health
POST /api/v1/wake
GET  /api/v1/wake/{request_id}
```

El cuerpo del `POST` es:

```json
{"contract_version": 1, "request_id": "identificador-unico"}
```

La operación devuelve `accepted`, luego `packet_sent` y finalmente `ssh_open` o
`failed`. Repetir un `request_id` devuelve la misma operación y no vuelve a emitir
el paquete. Mientras hay una operación activa, otro identificador recibe `409`.

La API no se publica por TCP. El Compose monta `./volumes/wol-control` únicamente
en Lechu y este servicio. El contenedor expone su salud consultando `/health` por
el mismo socket.
