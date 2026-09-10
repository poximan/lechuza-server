FROM python:3.12.11-slim-bookworm AS python-deps
WORKDIR /workspace/charito-service
COPY shared/timeauthority-pkg /workspace/shared/timeauthority-pkg
COPY charito-service/requirements.txt ./requirements.txt
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir -r requirements.txt

FROM python:3.12.11-slim-bookworm

RUN groupadd --gid 1000 appgroup && \
    useradd --uid 1000 --gid 1000 --create-home --shell /bin/sh appuser

WORKDIR /app

COPY --chown=1000:1000 shared /shared
COPY --from=python-deps /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY --chown=1000:1000 charito-service/src /app/src

ENV PYTHONPATH=/app/src:/shared \
    PYTHONUNBUFFERED=1 \
    TZ=America/Argentina/Buenos_Aires

EXPOSE 8082

USER 1000:1000


CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8082"]
