#!/bin/sh
set -e

cd /app/backend

python manage.py migrate --noinput

case "$1" in
  web|"")
    python manage.py collectstatic --noinput >/dev/null 2>&1 || true
    exec gunicorn config.wsgi:application \
      --bind 0.0.0.0:8000 \
      --workers 4 \
      --threads 2 \
      --timeout 300 \
      --keep-alive 5 \
      --max-requests 1000 \
      --max-requests-jitter 50 \
      --access-logfile - \
      --error-logfile - \
      --log-level info
    ;;
  celery)
    shift
    exec celery -A config worker -l info --concurrency=4 "$@"
    ;;
  celery_beat)
    shift
    exec celery -A config beat -l info --scheduler celery.beat:PersistentScheduler "$@"
    ;;
  telegram_bot)
    shift
    exec python -m orders.telegram_bot
    ;;
  *)
    exec "$@"
    ;;
esac

