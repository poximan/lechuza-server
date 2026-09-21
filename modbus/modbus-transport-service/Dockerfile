FROM python:3.12.11-slim-bookworm AS deps
WORKDIR /workspace/modbus-transport-service
COPY shared/timeauthority-pkg /workspace/shared/timeauthority-pkg
COPY modbus/modbus-transport-service/requirements.txt ./requirements.txt
RUN python -m venv /opt/venv && /opt/venv/bin/pip install --no-cache-dir -r requirements.txt

FROM python:3.12.11-slim-bookworm
WORKDIR /app
ENV PYTHONUNBUFFERED=1 TZ=UTC PATH="/opt/venv/bin:$PATH"
COPY --from=deps /opt/venv /opt/venv
RUN groupadd --gid 1000 appgroup && useradd --uid 1000 --gid 1000 --create-home --shell /bin/sh appuser
COPY --chown=1000:1000 modbus/modbus-transport-service/src ./src
USER 1000:1000
EXPOSE 8084
CMD ["uvicorn", "src.app:app", "--host", "0.0.0.0", "--port", "8084"]
