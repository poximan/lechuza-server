FROM python:3.12-slim

RUN groupadd --gid 1000 appgroup && \
    useradd --uid 1000 --gid 1000 --create-home --shell /bin/sh appuser

WORKDIR /app

COPY shared /shared
COPY charito-service/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY --chown=1000:1000 charito-service/src /app/src

ENV PYTHONPATH=/app/src:/shared \
    PYTHONUNBUFFERED=1 \
    TZ=America/Argentina/Buenos_Aires

EXPOSE 8082

USER 1000:1000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8082/health', timeout=4)"

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8082"]
