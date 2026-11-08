FROM python:3.12.12-slim-trixie

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl libgomp1 \
    && apt-get clean && find /var/lib/apt/lists -type f -delete

WORKDIR /app
COPY ai_service/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY ai_service/app ./app

RUN useradd --uid 10001 --create-home appuser
USER appuser

EXPOSE 8001
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001", \
     "--ssl-keyfile", "/certs/ai_service.key", "--ssl-certfile", "/certs/ai_service.crt"]
