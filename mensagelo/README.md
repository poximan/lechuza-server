# mensagelo

API FastAPI para envio de correo y registro operativo en SQLite.

## Componentes

| Archivo | Responsabilidad |
| --- | --- |
| `app.py` | API, autenticacion y ciclo de la cola. |
| `mailer.py` | SMTP, TLS y reintentos. |
| `queue_worker.py` | Procesamiento asincronico. |
| `db.py` | Persistencia de envios. |
| `config.py` | Variables obligatorias. |

## Endpoints

- `POST /send`: envio sincrono autenticado con `X-API-Key`.
- `POST /send_async`: encola y responde `202`; devuelve `503` si la cola esta llena.
- `GET /health`: estado publico del servicio.

El flujo sincrono confirma el resultado SMTP antes de responder. El asincrono confirma la aceptacion en cola y registra el resultado cuando el worker termina.
