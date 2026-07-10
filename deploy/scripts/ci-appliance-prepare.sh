#!/usr/bin/env bash
# Activate dev-on on the appliance host using CI-built frontend/dist (from build-frontend).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

APPLIANCE_BASE_URL="${APPLIANCE_BASE_URL:-https://localhost:8443}"
FRONTEND_DIST="${ROOT}/frontend/dist"

if [[ -z "${APPLIANCE_ADMIN_PASSWORD:-}" ]]; then
  echo "APPLIANCE_ADMIN_PASSWORD is required" >&2
  exit 1
fi

if [[ ! -f "${FRONTEND_DIST}/index.html" ]]; then
  echo "ERROR: ${FRONTEND_DIST}/index.html not found (expected build-frontend artifact)" >&2
  exit 1
fi

# Docker-built artifacts may land with ownership the shell runner cannot lchown; ensure readable.
chmod -R u+rwX "${FRONTEND_DIST}" 2>/dev/null || true

export DEV_MODE_SKIP_FRONTEND_BUILD=1
"${SCRIPT_DIR}/nunet-web-mode.sh" dev-on

sleep 10
curl -kSf "${APPLIANCE_BASE_URL}/health"
echo "Appliance dev-on health check passed."
