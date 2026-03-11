#!/usr/bin/env bash
# Remote dev smoke test: verifies key backend endpoints on the appliance box.
# Expects the repo at /opt/nunet/appliance-dev (override APPLIANCE_ROOT or edit .env).
# Copy .env.example to .env and adjust values before running.
set -euo pipefail

ROOT_DIR=${APPLIANCE_ROOT:-/opt/nunet/appliance-dev}

cd "$ROOT_DIR"

if [ -f ".env" ]; then
  export $(grep -v '^#' .env | xargs || true)
elif [ -f ".env.dev" ]; then
  export $(grep -v '^#' .env.dev | xargs || true)
fi

export APPLIANCE_ROOT=${APPLIANCE_ROOT:-$ROOT_DIR}
export BACKEND_PORT=${BACKEND_PORT:-8080}
BASE_URL=${BASE_URL:-"http://127.0.0.1:${BACKEND_PORT}"}

check_endpoint() {
  local path="$1"
  echo "Checking ${BASE_URL}${path} ..."
  curl -fsS -m 10 "${BASE_URL}${path}" >/dev/null
}

check_endpoint "/health"
check_endpoint "/dms/status"

echo "Smoke checks passed against ${BASE_URL}"
