#!/bin/sh
set -eu

DB_PATH="${DJANGO_DB_PATH:-/app/db.sqlite3}"
mkdir -p "$(dirname "$DB_PATH")"

uv run python manage.py migrate --noinput

BUCKET_READY_ATTEMPTS="${ANSWER_PHOTO_BUCKET_READY_ATTEMPTS:-15}"
attempt_number=1
while true; do
    if uv run python manage.py ensure_answer_photo_bucket; then
        break
    fi

    if [ "$attempt_number" -ge "$BUCKET_READY_ATTEMPTS" ]; then
        echo "Answer photo bucket setup failed after $attempt_number attempts." >&2
        exit 1
    fi

    attempt_number=$((attempt_number + 1))
    sleep 2
done

APP_SERVER="${DJANGO_APP_SERVER:-gunicorn}"
if [ "$APP_SERVER" = "runserver" ]; then
    exec uv run python manage.py runserver 0.0.0.0:8000
fi

STATIC_ROOT="${DJANGO_STATIC_ROOT:-/data/static}"
mkdir -p "$STATIC_ROOT"
uv run python manage.py collectstatic --noinput

APP_MODULE="${DJANGO_WSGI_MODULE:-agentic_curiosity.wsgi:application}"
BIND="${GUNICORN_BIND:-0.0.0.0:8000}"
WORKERS="${GUNICORN_WORKERS:-3}"
TIMEOUT="${GUNICORN_TIMEOUT:-60}"

exec uv run gunicorn "$APP_MODULE" \
    --bind "$BIND" \
    --workers "$WORKERS" \
    --timeout "$TIMEOUT" \
    --access-logfile - \
    --error-logfile -
