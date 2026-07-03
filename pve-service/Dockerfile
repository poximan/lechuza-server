FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1
COPY shared /shared
ENV PYTHONPATH="/shared:${PYTHONPATH}"
COPY pve-service/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
RUN groupadd --gid 1000 appgroup && \
    useradd --uid 1000 --gid 1000 --create-home --shell /bin/sh appuser
COPY pve-service/src ./src
RUN chown -R 1000:1000 /app
USER 1000:1000
EXPOSE 8083
CMD ["uvicorn", "src.app:app", "--host", "0.0.0.0", "--port", "8083"]
