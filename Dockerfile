FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libjpeg-dev zlib1g-dev libpq-dev gettext \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean


COPY requirements.txt /tmp/requirements.txt
RUN pip install --upgrade pip \
    && pip install -r /tmp/requirements.txt


COPY backend /app/backend
COPY backend/entrypoint.sh /entrypoint.sh

RUN mkdir -p /app/backend/media /app/backend/logs && chmod +x /entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["/entrypoint.sh"]
CMD ["web"]

