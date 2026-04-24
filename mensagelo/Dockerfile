FROM python:3.12-slim-bookworm

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

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
RUN useradd -m -u 10002 appsvc

# código
COPY mensagelo/email_service /app/email_service

USER appsvc

EXPOSE 8081

CMD ["python", "-m", "email_service.main"]
