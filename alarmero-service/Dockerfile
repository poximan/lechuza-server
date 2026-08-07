FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=America/Argentina/Buenos_Aires \
    SERVICE_HOST=0.0.0.0 \
    SERVICE_PORT=8094

WORKDIR /app
COPY shared /shared
ENV PYTHONPATH="/shared:${PYTHONPATH}"
COPY alarmero-service/requirements.txt /app/requirements.txt
RUN pip install --no-compile -r /app/requirements.txt
RUN groupadd --gid 1000 appgroup && \
    useradd --uid 1000 --gid 1000 --create-home --shell /bin/sh appuser
COPY alarmero-service/backend /app/backend
COPY alarmero-service/frontend /app/frontend
RUN chown -R 1000:1000 /app
USER 1000:1000
EXPOSE 8094
CMD ["uvicorn", "backend.app:app", "--host", "0.0.0.0", "--port", "8094"]
