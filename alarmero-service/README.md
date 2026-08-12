# alarmero-service

Vista consolidada y solo de lectura del ciclo de vida de alarmas. Panelexemys es
el unico responsable de detectar y resolver incidencias; Mensagelo es el unico
responsable del despacho de correo. Alarmero consume ambos contratos por HTTP y
mantiene su propio historial append-only en SQLite.

Estados visibles:

- `potential`: condicion detectada que aun no cumplio el tiempo de activacion.
- `active`: alarma confirmada.
- `recovering`: la condicion desaparecio, pendiente de 10 minutos sostenidos.
- `resolved`: incidencia finalizada o potencial descartada.

El estado `sent` confirma que Mensagelo termino el intercambio SMTP. No implica
entrega en la bandeja del destinatario, dato que SMTP no puede garantizar.

El tiempo historico de despeje se mide hasta la primera observacion normal que
inicia `recovering`; la incidencia solo pasa a `resolved` si esa normalidad se
mantiene durante los 10 minutos configurados.

El contenedor prepara el bind mount `/app/data` al iniciar y luego ejecuta Uvicorn
como el usuario sin privilegios `appuser` (UID 1000). Esto permite que SQLite cree
la base y sus archivos WAL aun cuando Docker haya creado inicialmente el directorio
del host como `root`.

## Frontend

La interfaz usa React, TypeScript estricto y Vite. Consume
`@servicoop/frontend-foundation` mediante un contexto Docker adicional limitado a
`platform/frontend-foundation`; no duplica tokens ni componentes.
El build genera archivos estáticos relativos para que funcionen detrás de
`/alarmero/` con strip de prefijo en edge-gateway.

## Mapa de la vista

Alarmero tiene una sola vista operativa; resumen, incidencias, frecuencia y despejes son secciones del mismo agregado, no pestañas independientes.

| Capa | Fuentes |
|---|---|
| Presentación | `frontend/src/App.tsx`, `frontend/src/components/*` |
| Estado y contrato frontend | `useAlarmeroData.ts`, `AlarmeroApiClient.ts`, `AlarmeroContractParser.ts` |
| API | `backend/alarm_api.py` |
| Servicio | `backend/alarm_service.py`, `backend/sync_worker.py` |
| DAO | `backend/db.py` |

`backend/app.py` solo compone el proceso. La metodología general está en `../../../../metodologia.txt`.
