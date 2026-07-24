FROM python:3.12-slim-bookworm

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
COPY shared /shared
ENV PYTHONPATH="/shared:${PYTHONPATH}"
COPY mensagelo/email_service/requirements.txt /app/requirements.txt
RUN pip install --no-compile -r /app/requirements.txt

# usuario no-root
RUN groupadd --gid 1000 appgroup && \
    useradd --uid 1000 --gid 1000 --create-home --shell /bin/sh appuser

# codigo
COPY mensagelo/email_service /app/email_service

RUN chown -R 1000:1000 /app

USER 1000:1000

EXPOSE 8081

HEALTHCHECK --interval=30s --timeout=5s --retries=5 \
    CMD curl -fsS http://localhost:8081/health

CMD ["python", "-m", "email_service.main"]
