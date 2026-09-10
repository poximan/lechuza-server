import logging
import threading
import queue
from . import mailer, db

logger = logging.getLogger(__name__)

class MailQueueWorker:
    def __init__(self, q: "queue.Queue[str]"):
        self.q = q
        self.last_error = None
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self):
        self._thread.start()

    def is_alive(self):
        return self._thread.is_alive()

    def stop(self):
        self._stop.set()
        self._thread.join(timeout=2)

    def _run(self):
        while not self._stop.is_set():
            try:
                key = self.q.get(timeout=0.5)
            except queue.Empty:
                key = None
            try:
                task = db.claim_message(key)
                self.last_error = None
                if task is None:
                    continue
                self._deliver(task)
            except Exception as exc:
                self.last_error = str(exc)
                logger.exception("Fallo del worker de correo; no se repite un envio incierto")
                self._stop.wait(1)

    def _deliver(self, task):
        error = ""
        try:
            mailer.send_email(task["recipients"], task["subject"], task["body"])
        except Exception as exc:
            error = str(exc)
            logger.exception("SMTP no pudo confirmar la entrega")
        # Si falla esta confirmacion, la fila queda processing. El arranque
        # la marca failed; nunca se vuelve a enviar automaticamente.
        db.complete_message(task["idempotency_key"], success=not error, error=error)
        db.log_message(task["subject"], task["body"], task["recipients"],
                       success=not error, message_type=task.get("message_type"))
        self.last_error = None
