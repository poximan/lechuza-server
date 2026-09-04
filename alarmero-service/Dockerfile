FROM node:24.18.0-alpine AS frontend-builder

WORKDIR /workspace/products/comunic-mon/lechuza-server/alarmero-service/frontend
COPY --from=frontend-foundation / /workspace/platform/frontend-foundation
COPY alarmero-service/frontend/package.json ./package.json
COPY alarmero-service/frontend/package-lock.json ./package-lock.json
COPY alarmero-service/frontend/tsconfig.json ./tsconfig.json
COPY alarmero-service/frontend/vite.config.ts ./vite.config.ts
COPY alarmero-service/frontend/index.html ./index.html
COPY alarmero-service/frontend/src ./src
RUN npm ci --ignore-scripts --no-audit --no-fund
RUN npm run build

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
COPY --chown=1000:1000 alarmero-service/backend /app/backend
COPY --from=frontend-builder --chown=1000:1000 \
    /workspace/products/comunic-mon/lechuza-server/alarmero-service/frontend/dist \
    /app/frontend
USER 1000:1000
EXPOSE 8094
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8094/health', timeout=4)"
CMD ["uvicorn", "backend.app:app", "--host", "0.0.0.0", "--port", "8094"]
