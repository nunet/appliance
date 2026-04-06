#!/usr/bin/env bash
# Remote dev helper: run the Vite dev server on the appliance box.
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
export FRONTEND_PORT=${FRONTEND_PORT:-5173}
PNPM_VERSION="${PNPM_VERSION:-10.33.0}"
PNPM_CMD=(corepack pnpm)

cd frontend

corepack prepare "pnpm@${PNPM_VERSION}" --activate

"${PNPM_CMD[@]}" install --frozen-lockfile

"${PNPM_CMD[@]}" run dev -- --host 0.0.0.0 --port "$FRONTEND_PORT"
