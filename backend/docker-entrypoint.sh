#!/bin/sh
set -eu

if [ "${RUN_MIGRATIONS:-true}" = "true" ]; then
    .venv/bin/alembic upgrade head
fi

if [ "$#" -gt 0 ]; then
    exec "$@"
fi

exec .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
