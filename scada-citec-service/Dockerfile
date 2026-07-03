FROM python:3.12-slim

WORKDIR /app

COPY shared /shared
COPY scada-citec-service/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt && rm /tmp/requirements.txt
RUN groupadd --gid 1000 appgroup && \
    useradd --uid 1000 --gid 1000 --create-home --shell /bin/sh appuser

COPY scada-citec-service/backend /app/backend
COPY scada-citec-service/frontend /app/frontend
RUN chown -R 1000:1000 /app

ENV PYTHONPATH=/app:/shared
EXPOSE 8094

USER 1000:1000

CMD ["uvicorn", "backend.app:app", "--host", "0.0.0.0", "--port", "8094"]
