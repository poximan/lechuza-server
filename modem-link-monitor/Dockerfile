FROM python:3.12-slim

WORKDIR /app

COPY shared /shared
COPY modem-link-monitor/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt && rm /tmp/requirements.txt
RUN groupadd --gid 1000 appgroup && \
    useradd --uid 1000 --gid 1000 --create-home --shell /bin/sh appuser

COPY modem-link-monitor/src /app/src
RUN chown -R 1000:1000 /app

ENV PYTHONPATH=/app:/shared \
    PYTHONUNBUFFERED=1 \
    TZ=America/Argentina/Buenos_Aires

EXPOSE 8086

USER 1000:1000

CMD ["uvicorn", "src.app:app", "--host", "0.0.0.0", "--port", "8086"]
