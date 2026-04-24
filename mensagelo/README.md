# Resumen de Arquitectura: Servicio de Correo Electronico

## 1.0 Vision General de la Arquitectura

Este documento describe la arquitectura del Servicio de Correo Electronico. El diseno busca una arquitectura desacoplada y robusta para una funcion critica como la comunicacion por correo electronico. Al separar responsabilidades y optimizar flujos, el sistema garantiza alta disponibilidad, resiliencia y escalabilidad.

El objetivo es ofrecer una API segura y confiable para el envio de correos electronicos, soportando operaciones sincronas (confirmacion inmediata) y asincronas (volumenes altos sin degradar experiencia).

Principios clave:

- Separacion de responsabilidades: `app` (API), `mailer` (SMTP), `db` (persistencia), `queue_worker` (procesamiento en segundo plano).
- Procesamiento asincrono: cola en memoria (queue.Queue) para delegar trabajo pesado a un worker.
- Configuracion externalizada: variables de entorno, en linea con Twelve-Factor App.
- Resiliencia: reintentos automaticos con espera exponencial al hablar con SMTP.

## 2.0 Componentes y Modulos

| Modulo/Archivo   | Responsabilidad principal |
|------------------|---------------------------|
| app.py           | Nucleo FastAPI; endpoints (/send, /send_async, /health); autenticacion; arranca cola/worker. |
| queue_worker.py  | Implementa MailQueueWorker; procesa tareas en segundo plano. |
| mailer.py        | Logica SMTP: construccion de correo, conexion TLS/SSL, autenticacion, reintentos. |
| db.py            | Persistencia SQLite; inicializa BD; registra cada envio. |
| config.py        | Configuracion via variables de entorno. |
| models.py        | Esquemas Pydantic (SendRequest, SendResponse). |
| main.py          | Punto de entrada; arranca Uvicorn con la app definida en app.py. |

## 3.0 API del Servicio

Endpoints:

- POST /send
  - Envio sincrono; espera hasta enviar a SMTP.
  - Autenticacion: header X-API-Key.
  - Error SMTP -> 500 con SendResponse(ok=False).

- POST /send_async
  - Envio asincrono; encola y responde 202 Accepted.
  - Si la cola esta llena -> 503 Service Unavailable.

- GET /health
  - Devuelve { "status": "ok" }.
  - Publico, sin autenticacion.

## 4.0 Flujos de Envio

Flujo sincrono: valida API_KEY -> envia correo -> registra en BD -> responde 200/500. Confirmacion definitiva pero con mas latencia.

Flujo asincrono: valida API_KEY -> encola -> responde 202 -> worker procesa. Menor latencia, mayor resistencia a carga.

