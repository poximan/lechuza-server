FROM python:3.12-slim

WORKDIR /app

COPY shared /shared
COPY router-telef-service/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt && rm /tmp/requirements.txt

COPY router-telef-service/src /app/src

ENV PYTHONPATH=/app:/shared

CMD ["uvicorn", "src.app:app", "--host", "0.0.0.0", "--port", "8086"]
