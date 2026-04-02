#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

ENV_FILE="${E2E_ENV_FILE:-$ROOT_DIR/.env.e2e}"
if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  . "$ENV_FILE"
  set +a
fi

CYPRESS_BASE_URL="${CYPRESS_BASE_URL:-http://localhost:5173}"
CYPRESS_BACKEND_BASE_URL="${CYPRESS_BACKEND_BASE_URL:-http://localhost:8080}"
CYPRESS_ADMIN_PASSWORD="${CYPRESS_ADMIN_PASSWORD:-nunettest}"
CYPRESS_IMAGE="${CYPRESS_IMAGE:-cypress/included:13.15.2}"

SPECS_DEFAULT="cypress/e2e/join-org-mailhog.cy.ts,cypress/e2e/offboard-onboard.cy.ts,cypress/e2e/deployments.cy.ts,cypress/e2e/ensembles.cy.ts,cypress/e2e/org-leave.cy.ts"
CYPRESS_SPECS="${CYPRESS_SPECS:-$SPECS_DEFAULT}"

PNPM_VERSION="${PNPM_VERSION:-10.33.0}"

DOCKER_NETWORK="${DOCKER_NETWORK:-}"
DOCKER_ARGS=()
if [[ -n "$DOCKER_NETWORK" ]]; then
  DOCKER_ARGS+=(--network "$DOCKER_NETWORK")
fi

docker run --rm -t \
  "${DOCKER_ARGS[@]}" \
  --entrypoint bash \
  -v "$ROOT_DIR:/e2e" \
  -v nunet-e2e-node-modules:/e2e/node_modules \
  -v nunet-e2e-pnpm-store:/pnpm-store \
  -v nunet-e2e-cypress-cache:/root/.cache/Cypress \
  -w /e2e \
  -e ELECTRON_RUN_AS_NODE= \
  -e CYPRESS_BASE_URL \
  -e CYPRESS_BACKEND_BASE_URL \
  -e CYPRESS_ADMIN_PASSWORD \
  -e CYPRESS_SETUP_TOKEN_PATH \
  -e CYPRESS_MAILHOG_BASE_URL \
  -e CYPRESS_MAILHOG_USERNAME \
  -e CYPRESS_MAILHOG_PASSWORD \
  -e CYPRESS_MAIL_INBOX_DOMAIN \
  -e CYPRESS_MAIL_SUBJECT_FRAGMENT \
  -e CYPRESS_MAIL_POLL_DELAY_MS \
  -e CYPRESS_MAIL_TIMEOUT_MS \
  -e CYPRESS_SPECS \
  -e CYPRESS_VERIFY_SSL \
  -e NODE_TLS_REJECT_UNAUTHORIZED \
  -e PNPM_STORE_DIR=/pnpm-store \
  -e XDG_RUNTIME_DIR=/tmp/xdg \
  "$CYPRESS_IMAGE" \
  -lc "mkdir -p /tmp/xdg && chmod 700 /tmp/xdg && corepack prepare pnpm@${PNPM_VERSION} --activate && corepack pnpm install --frozen-lockfile && corepack pnpm exec cypress install && corepack pnpm cy:run --browser electron --spec \"$CYPRESS_SPECS\""

status=$?
exit $status
