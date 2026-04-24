from fastapi import FastAPI, Header, HTTPException, status
from fastapi.responses import JSONResponse
from typing import Optional
import queue
import smtplib
import socket

from . import config, db, mailer
from .models import SendRequest, SendResponse
from .queue_worker import MailQueueWorker

app = FastAPI(title="Email Messaging Service", version="1.0.0")

# --- init DB ---
db.init_db()

# --- cola + worker ---
mail_queue: "queue.Queue[dict]" = queue.Queue(maxsize=config.QUEUE_MAXSIZE)
worker: Optional[MailQueueWorker] = None

def _auth_or_401(api_key_header: Optional[str]):
    if not api_key_header or api_key_header != config.API_KEY:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")

@app.on_event("startup")
def _on_startup():
    global worker
    if worker is None or not worker.is_alive():
        w = MailQueueWorker(mail_queue)
        w.daemon = True
        w.start()
        worker = w

@app.post("/send", response_model=SendResponse)
def send_email_sync(
    payload: SendRequest,
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
):
    _auth_or_401(x_api_key)

    try:
        mailer.send_email(payload.recipients, payload.subject, payload.body)
        db.log_message(payload.subject, payload.body, payload.recipients, success=True, message_type=payload.message_type)
        return SendResponse(ok=True, queued=False, message="Email enviado")
    except Exception as e:
        db.log_message(payload.subject, payload.body, payload.recipients, success=False, message_type=payload.message_type)
        return JSONResponse(
            status_code=500,
            content=SendResponse(ok=False, queued=False, message=f"Fallo SMTP: {e}").model_dump()
        )

@app.post("/send_async", response_model=SendResponse, status_code=202)
def send_email_async(
    payload: SendRequest,
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
):
    _auth_or_401(x_api_key)

    try:
        mail_queue.put_nowait(payload.model_dump())
        return SendResponse(ok=True, queued=True, message="Encolado para envio")
    except queue.Full:
        raise HTTPException(status_code=503, detail="Cola llena, intentar mas tarde")

@app.get("/smtppostserv")
def smtp_post_serv_check(
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
):
    """
    Chequeo activo del servidor SMTP configurado.
    Hace EHLO, STARTTLS si corresponde, login si hay credenciales y NOOP.
    Devuelve:
      {"status":"ok"} si responde correctamente,
      {"status":"down","reason":"..."} si no.
    """
    _auth_or_401(x_api_key)

    host = config.SMTP_SERVER
    port = config.SMTP_PORT
    username = config.SMTP_USERNAME
    password = config.SMTP_PASSWORD
    use_tls = config.SMTP_USE_TLS
    timeout = config.SMTP_TIMEOUT_SECONDS

    if not host or not port:
        return JSONResponse(status_code=503, content={"status": "down", "reason": "SMTP no configurado"})

    try:
        if use_tls:
            client = smtplib.SMTP(host, port, timeout=timeout)
            client.ehlo()
            client.starttls()
            client.ehlo()
        else:
            client = smtplib.SMTP_SSL(host, port, timeout=timeout)

        if username:
            client.login(username, password or "")

        code, _ = client.noop()
        try:
            client.quit()
        except Exception:
            pass

        if 200 <= code < 400:
            return {"status": "ok"}
        return JSONResponse(status_code=503, content={"status": "down", "reason": f"NOOP rc={code}"})

    except (smtplib.SMTPException, OSError, socket.error) as e:
        return JSONResponse(status_code=503, content={"status": "down", "reason": f"smtp/os error: {e}"})
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "down", "reason": f"excepcion: {e}"})

@app.get("/health")
def health():
    return {"status": "ok"}
