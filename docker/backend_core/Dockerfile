FROM python:3.12.12-slim-trixie

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app

# Клиент PostgreSQL той же основной версии, что и сервер (pg_dump/pg_restore для резервного копирования)
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl postgresql-client-17 \
    && apt-get clean && find /var/lib/apt/lists -type f -delete

WORKDIR /app
COPY backend_core/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY backend_core/app ./app
COPY scripts ./scripts

RUN useradd --uid 10001 --create-home appuser && mkdir -p /backups && chown appuser /backups
USER appuser

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--ssl-keyfile", "/certs/backend_core.key", "--ssl-certfile", "/certs/backend_core.crt", \
     "--proxy-headers", "--forwarded-allow-ips", "*"]
