FROM python:3.12.11-slim-bookworm AS python-deps
WORKDIR /workspace/mensagelo/email_service
COPY shared/timeauthority-pkg /workspace/shared/timeauthority-pkg
COPY mensagelo/email_service/requirements.txt ./requirements.txt
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir -r requirements.txt

FROM python:3.12.11-slim-bookworm

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=America/Argentina/Buenos_Aires \
    SERVICE_HOST=0.0.0.0 \
    SERVICE_PORT=8081

RUN set -eux; \
    printf "deb https://deb.debian.org/debian bookworm main\n" > /etc/apt/sources.list; \
    printf "deb https://deb.debian.org/debian bookworm-updates main\n" >> /etc/apt/sources.list; \
    printf "deb https://security.debian.org/debian-security bookworm-security main\n" >> /etc/apt/sources.list; \
    apt-get update && \
    apt-get install -y --no-install-recommends curl tzdata && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# deps primero para cache
COPY --chown=1000:1000 shared /shared
ENV PYTHONPATH="/shared:${PYTHONPATH}"
COPY --from=python-deps /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# usuario no-root
RUN groupadd --gid 1000 appgroup && \
    useradd --uid 1000 --gid 1000 --create-home --shell /bin/sh appuser

# codigo
COPY --chown=1000:1000 mensagelo/email_service /app/email_service

USER 1000:1000

EXPOSE 8081


CMD ["python", "-m", "email_service.main"]
