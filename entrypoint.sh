#!/bin/sh
set -eu

exec gunicorn app.main:app \
  -k uvicorn.workers.UvicornWorker \
  --workers "${WEB_CONCURRENCY:-2}" \
  --bind 0.0.0.0:8001 \
  --timeout "${GUNICORN_TIMEOUT_SECONDS:-90}" \
  --graceful-timeout "${GUNICORN_GRACEFUL_SECONDS:-30}" \
  --keep-alive "${GUNICORN_KEEPALIVE_SECONDS:-5}" \
  --forwarded-allow-ips="${FORWARDED_ALLOW_IPS:-*}"