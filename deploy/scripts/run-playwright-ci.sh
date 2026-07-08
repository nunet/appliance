#!/usr/bin/env bash
# Run Playwright E2E against a live appliance (local CI parity or GitLab job).
#
# Usage (from repo user, after setting APPLIANCE_ADMIN_PASSWORD and optionally APPLIANCE_BASE_URL):
#   ./deploy/scripts/run-playwright-ci.sh
#   ./deploy/scripts/run-playwright-ci.sh playwright/login-and-dashboard.spec.ts
#
# Default: Docker + official Playwright image (Chromium isolated from the appliance host).
#   RUN_PLAYWRIGHT_NATIVE=1  — run pnpm e2e on the host (requires local playwright install).
#   RUN_PLAYWRIGHT_IN_DOCKER=1 — force Docker even when CI is set.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
USER="$(cd "$SCRIPT_DIR/../.." && pwd)"
FRONTEND_DIR="$USER/frontend"

PLAYWRIGHT_IMAGE="${PLAYWRIGHT_IMAGE:-mcr.microsoft.com/playwright:v1.60.0-jammy}"
PNPM_VERSION="${PNPM_VERSION:-10.34.4}"
DEFAULT_BASE_URL="https://localhost:8443"

if [[ -f "$USER/.env.test" ]]; then
  set -a
  # shellcheck source=/dev/null
  source "$USER/.env.test"
  set +a
fi

export APPLIANCE_BASE_URL="${APPLIANCE_BASE_URL:-$DEFAULT_BASE_URL}"

if [[ -z "${APPLIANCE_ADMIN_PASSWORD:-}" ]]; then
  echo "APPLIANCE_ADMIN_PASSWORD is required (set in env or $USER/.env.test)" >&2
  exit 1
fi

run_native() {
  cd "$FRONTEND_DIR"
  corepack prepare "pnpm@${PNPM_VERSION}" --activate
  corepack pnpm install --frozen-lockfile --config.confirmModulesPurge=false
  exec corepack pnpm e2e --workers=1 "$@"
}

use_docker=1
if [[ "${RUN_PLAYWRIGHT_NATIVE:-}" == "1" ]]; then
  use_docker=0
elif [[ -n "${CI:-}" && "${RUN_PLAYWRIGHT_IN_DOCKER:-}" != "1" ]]; then
  use_docker=0
fi

if [[ "$use_docker" -eq 0 ]]; then
  run_native "$@"
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "docker is required for containerized Playwright (or set RUN_PLAYWRIGHT_NATIVE=1)" >&2
  exit 1
fi

docker_network=()
if [[ "$APPLIANCE_BASE_URL" =~ ^https?://(localhost|127\.0\.0\.1)([:/]|$) ]]; then
  docker_network=(--network host)
fi

docker_env=(
  -e "APPLIANCE_BASE_URL=${APPLIANCE_BASE_URL}"
  -e "APPLIANCE_ADMIN_PASSWORD=${APPLIANCE_ADMIN_PASSWORD}"
  -e "PNPM_VERSION=${PNPM_VERSION}"
)

optional_env=(
  MAILHOG_USERNAME
  MAILHOG_PASSWORD
  MAILHOG_BASE_URL
  MAIL_INBOX_DOMAIN
  MAIL_SUBJECT_FRAGMENT
  MAIL_POLL_DELAY_MS
  MAIL_TIMEOUT_MS
  NUTEST_ORG_DID
  NUTEST_ROLE
  ENSEMBLE_SKIP_DESTRUCTIVE
  DEPLOYMENTS_SKIP
)

for var in "${optional_env[@]}"; do
  if [[ -n "${!var:-}" ]]; then
    docker_env+=(-e "${var}=${!var}")
  fi
done

quoted_args=""
if (("$#" > 0)); then
  quoted_args="$(printf '%q ' "$@")"
fi

docker run --rm \
  --user $(id -u):$(id -g) \
  "${docker_network[@]}" \
  -v "${USER}:/work" \
  -w /work/frontend \
  "${docker_env[@]}" \
  "$PLAYWRIGHT_IMAGE" \
  bash -lc "
    set -euo pipefail
    corepack prepare \"pnpm@${PNPM_VERSION}\" --activate
    corepack pnpm install --frozen-lockfile --config.confirmModulesPurge=false
    exec corepack pnpm e2e --workers=1 \"\$@\"
  " _ "$@"
