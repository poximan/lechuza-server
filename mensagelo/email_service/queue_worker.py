import threading
import queue
from typing import Dict, Any
from . import mailer, db

class MailQueueWorker:
    def __init__(self, q: "queue.Queue[Dict[str, Any]]"):
        self.q = q
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self):
        self._thread.start()

    def stop(self):
        self._stop.set()
        self._thread.join(timeout=2)

    def _run(self):
        while not self._stop.is_set():
            try:
                task = self.q.get(timeout=0.5)
            except queue.Empty:
                continue
            try:
                recipients = task["recipients"]
                subject = task["subject"]
                body = task["body"]
                msg_type = task.get("message_type")
                mailer.send_email(recipients, subject, body)
                db.log_message(subject, body, recipients, success=True, message_type=msg_type)
            except Exception:
                # si falla, lo registramos como failed
                try:
                    db.log_message(task.get("subject",""), task.get("body",""), task.get("recipients",[]), success=False, message_type=task.get("message_type"))
                except Exception:
                    pass