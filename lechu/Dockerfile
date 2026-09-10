FROM python:3.12.11-slim-bookworm AS python-deps
WORKDIR /workspace/lechu
COPY shared/timeauthority-pkg /workspace/shared/timeauthority-pkg
COPY lechu/requirements.txt ./requirements.txt
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir -r requirements.txt

# lechu/Dockerfile
FROM node:24.18.0-alpine AS frontend-builder

WORKDIR /workspace/products/comunic-mon/lechuza-server/lechu/frontend

COPY --from=frontend-foundation / /workspace/platform/frontend-foundation
COPY lechu/frontend/package.json ./package.json
COPY lechu/frontend/package-lock.json ./package-lock.json
COPY lechu/frontend/tsconfig.json ./tsconfig.json
COPY lechu/frontend/vite.config.ts ./vite.config.ts
COPY lechu/frontend/index.html ./index.html
COPY lechu/frontend/src ./src
COPY lechu/src/assets ../src/assets

RUN npm ci --ignore-scripts --no-audit --no-fund
RUN npm run build

FROM python:3.12.11-slim-bookworm

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=America/Argentina/Buenos_Aires \
    LECHU_HOST=0.0.0.0 \
    LECHU_PORT=8052

RUN set -eux; \
    printf "deb https://deb.debian.org/debian bookworm main\n" > /etc/apt/sources.list; \
    printf "deb https://deb.debian.org/debian bookworm-updates main\n" >> /etc/apt/sources.list; \
    printf "deb https://security.debian.org/debian-security bookworm-security main\n" >> /etc/apt/sources.list; \
    apt-get update && \
    apt-get install -y --no-install-recommends iputils-ping curl tzdata && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --chown=1000:1000 shared /shared
ENV PYTHONPATH="/shared:${PYTHONPATH}"
COPY --from=python-deps /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

RUN groupadd --gid 1000 appgroup && \
    useradd --uid 1000 --gid 1000 --create-home --shell /bin/sh appuser

COPY --chown=1000:1000 lechu/src /app/src
COPY --chown=1000:1000 lechu/config.py /app/config.py
COPY --from=frontend-builder --chown=1000:1000 /workspace/products/comunic-mon/lechuza-server/lechu/frontend/dist /app/frontend

USER 1000:1000

EXPOSE 8052


CMD ["python", "-m", "src.start_server"]
