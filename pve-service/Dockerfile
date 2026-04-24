FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1
COPY shared /shared
ENV PYTHONPATH="/shared:${PYTHONPATH}"
COPY pve-service/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY pve-service/src ./src
EXPOSE 8083
CMD ["uvicorn", "src.app:app", "--host", "0.0.0.0", "--port", "8083"]
