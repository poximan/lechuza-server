FROM python:3.12-slim

WORKDIR /app

COPY shared /shared
COPY router-telef-service/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt && rm /tmp/requirements.txt
RUN groupadd --gid 1000 appgroup && \
    useradd --uid 1000 --gid 1000 --create-home --shell /bin/sh appuser

COPY router-telef-service/src /app/src
RUN chown -R 1000:1000 /app

ENV PYTHONPATH=/app:/shared

USER 1000:1000

CMD ["uvicorn", "src.app:app", "--host", "0.0.0.0", "--port", "8086"]
