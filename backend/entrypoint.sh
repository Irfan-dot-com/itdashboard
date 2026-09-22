#!/bin/sh
set -e

echo "Running database migrations..."
python -m alembic upgrade head

echo "Starting API..."
exec python -m uvicorn app.main:app \
    --host 0.0.0.0 \
    --port 4000 \
    --workers 2 \
    --log-level "${LOG_LEVEL:-info}"
