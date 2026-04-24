FROM python:3.12-slim

WORKDIR /app

COPY shared /shared
COPY scada-citec-service/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt && rm /tmp/requirements.txt

COPY scada-citec-service/backend /app/backend
COPY scada-citec-service/frontend /app/frontend

ENV PYTHONPATH=/app:/shared
EXPOSE 8094

CMD ["uvicorn", "backend.app:app", "--host", "0.0.0.0", "--port", "8094"]
