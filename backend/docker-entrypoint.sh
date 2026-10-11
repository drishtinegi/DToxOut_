#!/bin/sh
# Container entrypoint: apply DB migrations, then start the API server.
set -e

if [ "${RUN_MIGRATIONS:-true}" = "true" ]; then
  echo "[entrypoint] Applying database migrations..."
  prisma migrate deploy
fi

PORT="${PORT:-8000}"
WORKERS="${WEB_CONCURRENCY:-2}"

echo "[entrypoint] Starting API on :${PORT} with ${WORKERS} worker(s)"
exec gunicorn main:app \
  --worker-class uvicorn.workers.UvicornWorker \
  --workers "${WORKERS}" \
  --bind "0.0.0.0:${PORT}" \
  --timeout 60 \
  --graceful-timeout 30 \
  --keep-alive 5 \
  --forwarded-allow-ips="*" \
  --access-logfile - 
