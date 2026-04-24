FROM python:3.12-slim

RUN useradd --create-home --shell /bin/bash charito

WORKDIR /app

COPY shared /shared
COPY charito-service/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY charito-service/src /app/src

ENV PYTHONPATH=/app/src:/shared

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8082"]
