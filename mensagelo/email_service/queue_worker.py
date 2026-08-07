import threading
import queue
from . import mailer, db

class MailQueueWorker:
    def __init__(self, q: "queue.Queue[str]"):
        self.q = q
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
            idempotency_key = None
            try:
                idempotency_key = self.q.get(timeout=0.5)
            except queue.Empty:
                pass

            task = db.claim_message(idempotency_key)
            if task is None:
                task = db.claim_message()
            if task is None:
                continue

            recipients = task["recipients"]
            subject = task["subject"]
            body = task["body"]
            msg_type = task.get("message_type")
            try:
                mailer.send_email(recipients, subject, body)
                db.complete_message(task["idempotency_key"], success=True)
            except Exception as exc:
                try:
                    db.complete_message(
                        task["idempotency_key"],
                        success=False,
                        error=str(exc),
                    )
                    db.log_message(
                        task.get("subject", ""),
                        task.get("body", ""),
                        task.get("recipients", []),
                        success=False,
                        message_type=task.get("message_type"),
                    )
                except Exception:
                    pass
            else:
                try:
                    db.log_message(
                        subject,
                        body,
                        recipients,
                        success=True,
                        message_type=msg_type,
                    )
                except Exception:
                    pass
