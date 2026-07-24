# panelexemys/Dockerfile
FROM python:3.12-slim-bookworm

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=America/Argentina/Buenos_Aires \
    PANELEXEMYS_HOST=0.0.0.0 \
    PANELEXEMYS_PORT=8052

RUN set -eux; \
    printf "deb https://deb.debian.org/debian bookworm main\n" > /etc/apt/sources.list; \
    printf "deb https://deb.debian.org/debian bookworm-updates main\n" >> /etc/apt/sources.list; \
    printf "deb https://security.debian.org/debian-security bookworm-security main\n" >> /etc/apt/sources.list; \
    apt-get update && \
    apt-get install -y --no-install-recommends iputils-ping curl tzdata && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY shared /shared
ENV PYTHONPATH="/shared:${PYTHONPATH}"
COPY panelexemys/requirements.txt /app/requirements.txt
RUN pip install --no-compile -r /app/requirements.txt

RUN groupadd --gid 1000 appgroup && \
    useradd --uid 1000 --gid 1000 --create-home --shell /bin/sh appuser

COPY panelexemys/src /app/src
COPY panelexemys/config.py /app/config.py

RUN chown -R 1000:1000 /app

USER 1000:1000

EXPOSE 8052

CMD ["python", "-m", "src.start_server"]
