FROM python:3.12.11-slim-bookworm AS python-deps
WORKDIR /workspace/i20api-service
COPY shared/timeauthority-pkg /workspace/shared/timeauthority-pkg
COPY i20api-service/requirements.txt ./requirements.txt
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir -r requirements.txt

FROM python:3.12.11-slim-bookworm
WORKDIR /app
COPY --from=python-deps /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH" PYTHONUNBUFFERED=1 TZ=America/Argentina/Buenos_Aires
RUN groupadd --gid 1000 appgroup \
    && useradd --uid 1000 --gid 1000 --create-home --shell /bin/sh appuser
COPY --chown=1000:1000 i20api-service/i20api /app/i20api
USER 1000:1000
CMD ["uvicorn", "i20api.app:app_factory", "--factory", "--host", "0.0.0.0", "--port", "8096"]
