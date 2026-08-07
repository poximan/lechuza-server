# mensagelo

API FastAPI para envio de correo y registro operativo en SQLite.

## Componentes

| Archivo | Responsabilidad |
| --- | --- |
| `app.py` | API, autenticacion y ciclo de la cola. |
| `mailer.py` | Unico intento SMTP y negociacion TLS. |
| `queue_worker.py` | Procesamiento asincronico. |
| `db.py` | Persistencia de envios. |
| `config.py` | Variables obligatorias. |

## Endpoints

- `POST /send`: envio sincrono autenticado con `X-API-Key`.
- `POST /send_async`: exige `Idempotency-Key`, persiste el pedido antes de responder
  `202` y devuelve el mismo resultado ante reintentos con igual contenido. Devuelve
  `409` si la clave cambia de contenido y `503` si la cola durable esta llena.
- `GET /internal/dispatches`: consulta autenticada de estados de despacho para
  `alarmero-service`; no expone la base SQLite.
- `GET /health`: estado publico del servicio.

El flujo sincrono confirma el resultado SMTP antes de responder. El asincrono confirma
la aceptacion durable y registra el resultado cuando el worker termina. Cada pedido SMTP
se intenta una sola vez: ante una respuesta SMTP ambigua se prioriza no duplicar el correo.
