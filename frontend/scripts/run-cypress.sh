#!/usr/bin/env bash
# Run Cypress from frontend/ with optional .env.e2e (same pattern as run-e2e-docker.sh).
#
# Does NOT use the Python venv — Cypress is Node-only (separate from backend pytest).
#
# Usage (from frontend/):
#   cp .env.e2e.example .env.e2e   # then edit URLs + CYPRESS_ADMIN_PASSWORD
#   Optional: set CYPRESS_REBUILD_FRONTEND=true in .env.e2e to run ./deploy/scripts/nunet-web-mode.sh rebuild before specs (see cypress.config.ts before:run).
#   After startup/rebuild, cypress.config waits CYPRESS_RUN_SETTLE_MS (default 30s) before specs so the host can cool down.
#   npx --yes pnpm@10.4.0 install --frozen-lockfile   # if node_modules missing
#   ./scripts/run-cypress.sh run --browser electron --spec cypress/e2e/real-appliance-dashboard.cy.ts
#   Or: pnpm cy:run:e2e:rebuild   # same as CYPRESS_REBUILD_FRONTEND=1
#
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

ENV_FILE="${E2E_ENV_FILE:-$ROOT_DIR/.env.e2e}"
if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  . "$ENV_FILE"
  set +a
else
  echo "Note: $ENV_FILE not found. Copy from .env.e2e.example and set CYPRESS_* vars." >&2
fi

# Align with Docker runner and README: self-signed appliance HTTPS
if [[ "${CYPRESS_VERIFY_SSL:-}" == "false" ]]; then
  export NODE_TLS_REJECT_UNAUTHORIZED=0
fi

LOCAL_CYPRESS="$ROOT_DIR/node_modules/.bin/cypress"
if [[ -x "$LOCAL_CYPRESS" ]]; then
  exec "$LOCAL_CYPRESS" "$@"
fi

if command -v pnpm >/dev/null 2>&1; then
  exec pnpm exec cypress "$@"
fi

echo "Cypress is not installed under frontend/node_modules." >&2
echo "From frontend/, run one of:" >&2
echo "  npx --yes pnpm@10.4.0 install --frozen-lockfile" >&2
echo "  corepack enable && corepack prepare pnpm@10.4.0 --activate && pnpm install --frozen-lockfile" >&2
exit 1
