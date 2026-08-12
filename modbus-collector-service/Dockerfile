FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    TZ=America/Argentina/Buenos_Aires
COPY shared /shared
ENV PYTHONPATH="/shared:${PYTHONPATH}"
COPY modbus-collector-service/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
RUN groupadd --gid 1000 appgroup && \
    useradd --uid 1000 --gid 1000 --create-home --shell /bin/sh appuser
COPY --chown=1000:1000 modbus-collector-service/src ./src
USER 1000:1000
EXPOSE 8084
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8084/health', timeout=4)"
CMD ["uvicorn", "src.app:app", "--host", "0.0.0.0", "--port", "8084"]
