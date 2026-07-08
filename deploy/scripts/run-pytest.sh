#!/usr/bin/env bash
# Run backend pytest with the same venv layout as devctl / nunet-web-mode (default: $REPO_USER/.venv)
# and PYTHONPATH so both `backend.*` and `modules.*` imports resolve.
#
# Usage (from repo user):
#   ./deploy/scripts/run-pytest.sh
#   ./deploy/scripts/run-pytest.sh -m "integration or contract"
#   ./deploy/scripts/run-pytest.sh backend/tests/test_environment_profile.py -v
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
USER="$(cd "$SCRIPT_DIR/../.." && pwd)"
VENV_DIR="${VENV_DIR:-$USER/.venv}"
export PYTHONPATH="${USER}:${USER}/backend"

if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  echo "No Python venv at $VENV_DIR" >&2
  echo "Create it and install API deps, e.g.:" >&2
  echo "  cd \"$USER\" && python3 -m venv .venv && .venv/bin/pip install -r backend/nunet_api/requirements.txt -r backend/requirements-test.txt" >&2
  echo "Or run: ./deploy/scripts/devctl.sh setup  (creates venv; no servers started)" >&2
  exit 1
fi

echo "Installing test dependencies into $VENV_DIR ..." >&2
if [[ -f "$USER/backend/requirements-test.txt" ]]; then
  "$VENV_DIR/bin/pip" install -q -r "backend/nunet_api/requirements.txt" -r "$USER/backend/requirements-test.txt"
else
  echo "No $USER/backend/requirements-test.txt file found" >&2
  exit 1
fi

cd "$USER"
if [[ $# -eq 0 ]]; then
  exec "$VENV_DIR/bin/python" -m pytest backend/tests/
else
  exec "$VENV_DIR/bin/python" -m pytest "$@"
fi
