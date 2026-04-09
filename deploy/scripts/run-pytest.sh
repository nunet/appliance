#!/usr/bin/env bash
# Run backend pytest with the same venv layout as devctl / nunet-web-mode (default: $REPO_ROOT/.venv)
# and PYTHONPATH so both `backend.*` and `modules.*` imports resolve.
#
# Usage (from repo root):
#   ./deploy/scripts/run-pytest.sh
#   ./deploy/scripts/run-pytest.sh -q --tb=short
#   ./deploy/scripts/run-pytest.sh backend/tests/test_environment_profile.py -v
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
VENV_DIR="${VENV_DIR:-$ROOT/.venv}"
export PYTHONPATH="${ROOT}:${ROOT}/backend"

if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  echo "No Python venv at $VENV_DIR" >&2
  echo "Create it and install API deps, e.g.:" >&2
  echo "  cd \"$ROOT\" && python3 -m venv .venv && . .venv/bin/activate && pip install -r backend/nunet_api/requirements.txt" >&2
  echo "Or run: ./deploy/scripts/devctl.sh dev up  (creates venv and installs deps)" >&2
  exit 1
fi

if ! "$VENV_DIR/bin/python" -c "import pytest" 2>/dev/null; then
  echo "Installing pytest and httpx into $VENV_DIR ..." >&2
  "$VENV_DIR/bin/pip" install -q pytest httpx
fi

cd "$ROOT"
if [[ $# -eq 0 ]]; then
  exec "$VENV_DIR/bin/python" -m pytest backend/tests/
else
  exec "$VENV_DIR/bin/python" -m pytest "$@"
fi
