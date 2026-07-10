#!/usr/bin/env bash
# Install CI-built .deb packages on the appliance host runner and verify health.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

APPLIANCE_BASE_URL="${APPLIANCE_BASE_URL:-https://localhost:8443}"

if [[ -z "${APPLIANCE_ADMIN_PASSWORD:-}" ]]; then
  echo "APPLIANCE_ADMIN_PASSWORD is required" >&2
  exit 1
fi

HOST_ARCH="$(dpkg --print-architecture)"
DIST_DIR="${CI_PROJECT_DIR:-$ROOT}/dist"

if [[ ! -d "$DIST_DIR" ]]; then
  echo "ERROR: dist/ not found at $DIST_DIR (expected build-packages artifacts)" >&2
  exit 1
fi

mapfile -t web_debs < <(find "$DIST_DIR" -maxdepth 1 -name "nunet-appliance-web_*_${HOST_ARCH}.deb" | sort)

if [[ ${#web_debs[@]} -eq 0 ]]; then
  echo "ERROR: missing web .deb for architecture ${HOST_ARCH} in $DIST_DIR" >&2
  ls -la "$DIST_DIR" || true
  exit 1
fi

web_deb="${web_debs[-1]}"

echo "Installing ${web_deb} ..."
sudo apt-get install -y "$web_deb"

if systemctl is-active --quiet nunet-appliance-web.service 2>/dev/null; then
  sudo systemctl restart nunet-appliance-web.service
else
  sudo systemctl start nunet-appliance-web.service || true
fi

sleep 10
curl -kSf "${APPLIANCE_BASE_URL}/health"
echo "Appliance deploy health check passed."
