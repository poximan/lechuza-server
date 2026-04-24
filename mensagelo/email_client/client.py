import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Optional

import requests
from logosaurio import Logosaurio
from . import config

logger = Logosaurio()


def _req_test_recipients() -> List[str]:
    raw = os.getenv("TEST_RECIPIENTS")
    if raw is None or not raw.strip():
        raise EnvironmentError("Falta variable obligatoria: TEST_RECIPIENTS")
    items = [item.strip() for item in raw.split(",") if item.strip()]
    if not items:
        raise EnvironmentError("TEST_RECIPIENTS no contiene destinatarios validos")
    return items

def _headers():
    return {"X-API-Key": config.API_KEY}

def send_sync(recipients: List[str], subject: str, body: str, message_type: Optional[str] = None):
    url = f"{config.SERVICE_BASE_URL}/send"
    payload = {"recipients": recipients, "subject": subject, "body": body, "message_type": message_type}
    r = requests.post(url, json=payload, headers=_headers(), timeout=30)
    r.raise_for_status()
    return r.json()

def send_async(recipients: List[str], subject: str, body: str, message_type: Optional[str] = None):
    url = f"{config.SERVICE_BASE_URL}/send_async"
    payload = {"recipients": recipients, "subject": subject, "body": body, "message_type": message_type}
    r = requests.post(url, json=payload, headers=_headers(), timeout=30)
    r.raise_for_status()
    return r.json()

def blast_async(
    recipients: List[str],
    subject_prefix: str,
    body_prefix: str,
    message_type: Optional[str] = "load_test",
    count: int = 10,
    max_workers: int = 5,
):
    """
    Dispara 'count' requests concurrentes a /send_async.
    - subject/body llevan un sufijo incremental para que puedas distinguirlos en logs/DB.
    - max_workers controla el paralelismo (por defecto 50).
    Retorna una lista de tuples (idx, ok, result|error_str).
    """
    results = []
    t0 = time.time()

    def _one(i: int):
        subj = f"{subject_prefix} #{i:03d}"
        body = f"{body_prefix} [#{i:03d}]"
        try:
            res = send_async(recipients, subj, body, message_type)
            return (i, True, res)
        except Exception as e:
            return (i, False, str(e))

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(_one, i): i for i in range(1, count + 1)}
        for fut in as_completed(futures):
            results.append(fut.result())

    elapsed = time.time() - t0

    # Resumen en consola
    ok_count = sum(1 for _, ok, _ in results if ok)
    err_count = count - ok_count
    logger.info("=== BLAST ASYNC DONE ===", origin="MENSAGELO/CLIENT")
    logger.info(
        "Total: %s | OK: %s | ERR: %s | Tiempo: %.2fs",
        count,
        ok_count,
        err_count,
        elapsed,
        origin="MENSAGELO/CLIENT",
    )

    # Log de errores (si los hubo)
    if err_count:
        logger.warning("Errores en envio async", origin="MENSAGELO/CLIENT")
        for idx, ok, info in sorted(results):
            if not ok:
                logger.error(" #%03d: %s", idx, info, origin="MENSAGELO/CLIENT")

    return sorted(results)

if __name__ == "__main__":
    # Ejemplo: dispara N /send_async en paralelo
    DESTS = _req_test_recipients()
    blast_async(
        recipients=DESTS,
        subject_prefix="Prueba Async",
        body_prefix="Hola! Esto es una prueba asíncrona concurrente.",
        message_type="test_async",
        count=50,
        max_workers=50,  # podés bajar/subir esto según tu máquina/servicio
    )
