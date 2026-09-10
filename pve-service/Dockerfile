FROM python:3.12.11-slim-bookworm AS python-deps
WORKDIR /workspace/pve-service
COPY shared/timeauthority-pkg /workspace/shared/timeauthority-pkg
COPY pve-service/requirements.txt ./requirements.txt
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir -r requirements.txt

FROM python:3.12.11-slim-bookworm
WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    TZ=America/Argentina/Buenos_Aires
COPY --chown=1000:1000 shared /shared
ENV PYTHONPATH="/shared:${PYTHONPATH}"
COPY --from=python-deps /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN groupadd --gid 1000 appgroup && \
    useradd --uid 1000 --gid 1000 --create-home --shell /bin/sh appuser
COPY --chown=1000:1000 pve-service/src ./src
USER 1000:1000
EXPOSE 8083
CMD ["uvicorn", "src.app:app", "--host", "0.0.0.0", "--port", "8083"]
