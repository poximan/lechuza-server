FROM python:3.12.11-slim-bookworm AS deps
WORKDIR /workspace/generator-collector-service
COPY shared/timeauthority-pkg /workspace/shared/timeauthority-pkg
COPY generator-collector-service/requirements.txt ./requirements.txt
RUN python -m venv /opt/venv && /opt/venv/bin/pip install --no-cache-dir -r requirements.txt
FROM python:3.12.11-slim-bookworm
WORKDIR /app
ENV PYTHONUNBUFFERED=1 TZ=UTC PYTHONPATH="/shared" PATH="/opt/venv/bin:$PATH"
COPY --from=deps /opt/venv /opt/venv
COPY --chown=1000:1000 shared /shared
RUN groupadd --gid 1000 appgroup && useradd --uid 1000 --gid 1000 --create-home --shell /bin/sh appuser
COPY --chown=1000:1000 generator-collector-service/src ./src
USER 1000:1000
EXPOSE 8088
CMD ["uvicorn", "src.app:app", "--host", "0.0.0.0", "--port", "8088"]
