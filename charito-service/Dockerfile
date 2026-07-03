FROM python:3.12-slim

RUN groupadd --gid 1000 appgroup && \
    useradd --uid 1000 --gid 1000 --create-home --shell /bin/sh appuser

WORKDIR /app

COPY shared /shared
COPY charito-service/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY charito-service/src /app/src
RUN chown -R 1000:1000 /app

ENV PYTHONPATH=/app/src:/shared

USER 1000:1000

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8082"]
