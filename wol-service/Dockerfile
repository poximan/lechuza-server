FROM python:3.12.11-slim-bookworm AS python-deps
WORKDIR /workspace/wol-service
COPY shared/timeauthority-pkg /workspace/shared/timeauthority-pkg
COPY wol-service/requirements.txt ./requirements.txt
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir -r requirements.txt

FROM python:3.12.11-slim-bookworm
WORKDIR /app
COPY --from=python-deps /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ=UTC
RUN groupadd --gid 1000 appgroup \
    && useradd --uid 1000 --gid 1000 --create-home --shell /bin/sh appuser
COPY --chown=1000:1000 wol-service/src /app/src
USER 1000:1000
CMD ["python", "-m", "src.app"]
