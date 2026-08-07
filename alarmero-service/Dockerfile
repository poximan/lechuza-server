FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=America/Argentina/Buenos_Aires \
    SERVICE_HOST=0.0.0.0 \
    SERVICE_PORT=8094

WORKDIR /app
RUN apt-get update && \
    apt-get install -y --no-install-recommends gosu && \
    rm -rf /var/lib/apt/lists/*
COPY shared /shared
ENV PYTHONPATH="/shared:${PYTHONPATH}"
COPY alarmero-service/requirements.txt /app/requirements.txt
RUN pip install --no-compile -r /app/requirements.txt
RUN groupadd --gid 1000 appgroup && \
    useradd --uid 1000 --gid 1000 --create-home --shell /bin/sh appuser
COPY alarmero-service/backend /app/backend
COPY alarmero-service/frontend /app/frontend
COPY alarmero-service/docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chown -R 1000:1000 /app
RUN chmod 0755 /usr/local/bin/docker-entrypoint.sh
EXPOSE 8094
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
CMD ["uvicorn", "backend.app:app", "--host", "0.0.0.0", "--port", "8094"]
