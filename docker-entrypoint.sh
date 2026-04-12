#!/bin/sh
set -eu

DB_PATH="${DJANGO_DB_PATH:-/app/db.sqlite3}"
mkdir -p "$(dirname "$DB_PATH")"

uv run python manage.py migrate --noinput
exec uv run python manage.py runserver 0.0.0.0:8000
