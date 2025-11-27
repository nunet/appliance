#!/usr/bin/env bash
# Remote dev helper: run FastAPI with hot reload on the appliance box.
# Uses APPLIANCE_ROOT (defaults to this repo) or values from .env/.env.dev.
# Copy .env.example to .env and adjust values before running.
set -euo pipefail

ROOT_DIR=${APPLIANCE_ROOT:-$(cd "$(dirname "$0")/../.." && pwd)}

cd "$ROOT_DIR"

if [ -f ".env" ]; then
  export $(grep -v '^#' .env | xargs || true)
elif [ -f ".env.dev" ]; then
  export $(grep -v '^#' .env.dev | xargs || true)
fi

export APPLIANCE_ROOT=${APPLIANCE_ROOT:-$ROOT_DIR}
export NUNET_STATIC_DIR=${NUNET_STATIC_DIR:-"$APPLIANCE_ROOT/frontend/dist"}
export BACKEND_PORT=${BACKEND_PORT:-8080}

cd backend

if [ -d ".venv" ]; then
  . .venv/bin/activate
fi

gunicorn -k uvicorn.workers.UvicornWorker nunet_api.main:app \
  --bind "0.0.0.0:${BACKEND_PORT}" \
  --reload \
  --workers 1
