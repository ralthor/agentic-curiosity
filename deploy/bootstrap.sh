#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
ENV_FILE="$SCRIPT_DIR/.env"
COMPOSE_FILE="$SCRIPT_DIR/compose.yml"
NGINX_FILE="$SCRIPT_DIR/nginx.conf"
WRITE_ONLY=0

usage() {
    cat <<'EOF'
Usage: sh bootstrap.sh [--write-only]

Creates compose.yml and nginx.conf next to this script, then starts the stack.
Put a .env file in the same directory before running it.

Options:
  --write-only   Only write the deployment files; do not run Docker Compose.
EOF
}

require_env_key() {
    key="$1"
    if ! grep -Eq "^[[:space:]]*(export[[:space:]]+)?${key}=" "$ENV_FILE"; then
        echo "Missing ${key} in $ENV_FILE" >&2
        exit 1
    fi
}

compose() {
    if docker compose version >/dev/null 2>&1; then
        docker compose "$@"
        return
    fi

    if command -v docker-compose >/dev/null 2>&1; then
        docker-compose "$@"
        return
    fi

    echo "Docker Compose is not available. Install 'docker compose' or 'docker-compose' first." >&2
    exit 1
}

case "${1:-}" in
    "")
        ;;
    --write-only)
        WRITE_ONLY=1
        ;;
    -h|--help)
        usage
        exit 0
        ;;
    *)
        usage >&2
        exit 2
        ;;
esac

if [ ! -f "$ENV_FILE" ]; then
    echo "Expected $ENV_FILE. Copy .env.example to .env and fill in your values first." >&2
    exit 1
fi

require_env_key APP_IMAGE
require_env_key DJANGO_SECRET_KEY
require_env_key DJANGO_ALLOWED_HOSTS
require_env_key OPENAI_API_KEY

mkdir -p "$SCRIPT_DIR/docker-data/static" "$SCRIPT_DIR/redis-data" "$SCRIPT_DIR/minio-data"

cat >"$COMPOSE_FILE" <<'EOF'
services:
  web:
    image: ${APP_IMAGE:?Set APP_IMAGE in .env}
    restart: unless-stopped
    env_file:
      - .env
    environment:
      DJANGO_APP_SERVER: gunicorn
      DJANGO_DB_PATH: /data/db.sqlite3
      DJANGO_STATIC_ROOT: /data/static
      DJANGO_USE_X_FORWARDED_HOST: "true"
      DJANGO_TRUST_X_FORWARDED_PROTO: "true"
      GUNICORN_BIND: 0.0.0.0:8000
      AI_CHAT_OBJECT_STORAGE_ENDPOINT: ${AI_CHAT_OBJECT_STORAGE_ENDPOINT:-http://minio:9000}
      AI_CHAT_OBJECT_STORAGE_ACCESS_KEY: ${AI_CHAT_OBJECT_STORAGE_ACCESS_KEY:-minioadmin}
      AI_CHAT_OBJECT_STORAGE_SECRET_KEY: ${AI_CHAT_OBJECT_STORAGE_SECRET_KEY:-minioadmin}
      AI_CHAT_OBJECT_STORAGE_BUCKET: ${AI_CHAT_OBJECT_STORAGE_BUCKET:-student-answer-photos}
      AI_CHAT_OBJECT_STORAGE_REGION: ${AI_CHAT_OBJECT_STORAGE_REGION:-us-east-1}
    volumes:
      - ./docker-data:/data
    depends_on:
      - redis
      - minio
    expose:
      - "8000"

  redis:
    image: redis:7-alpine
    restart: unless-stopped
    command: ["redis-server", "--appendonly", "yes"]
    volumes:
      - ./redis-data:/data
    expose:
      - "6379"

  minio:
    image: minio/minio:latest
    restart: unless-stopped
    command: ["server", "/data", "--console-address", ":9001"]
    environment:
      MINIO_ROOT_USER: ${AI_CHAT_OBJECT_STORAGE_ACCESS_KEY:-minioadmin}
      MINIO_ROOT_PASSWORD: ${AI_CHAT_OBJECT_STORAGE_SECRET_KEY:-minioadmin}
    volumes:
      - ./minio-data:/data
    expose:
      - "9000"
      - "9001"

  nginx:
    image: nginx:1.27-alpine
    restart: unless-stopped
    depends_on:
      - web
    ports:
      - "${NGINX_HTTP_PORT:-80}:80"
    volumes:
      - ./nginx.conf:/etc/nginx/conf.d/default.conf:ro
      - ./docker-data/static:/srv/static:ro
EOF

cat >"$NGINX_FILE" <<'EOF'
server {
    listen 80;
    server_name _;

    client_max_body_size 40m;

    location /static/ {
        alias /srv/static/;
        access_log off;
        expires 1h;
        add_header Cache-Control "public";
    }

    location / {
        proxy_pass http://web:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Connection "";
        proxy_buffering off;
        proxy_read_timeout 120s;
        proxy_send_timeout 120s;
    }
}
EOF

echo "Wrote $COMPOSE_FILE"
echo "Wrote $NGINX_FILE"

if [ "$WRITE_ONLY" -eq 1 ]; then
    exit 0
fi

if ! command -v docker >/dev/null 2>&1; then
    echo "Docker is not installed." >&2
    exit 1
fi

cd "$SCRIPT_DIR"
compose config >/dev/null
compose up -d
