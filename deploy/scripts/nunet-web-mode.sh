#!/usr/bin/env bash
# Toggle nunet appliance web systemd service between packaged (PEX) execution
# and repo-backed development using a local venv + built frontend assets.
#
# Usage:
#   ./deploy/scripts/nunet-web-mode.sh dev-on
#   ./deploy/scripts/nunet-web-mode.sh dev-off
#   ./deploy/scripts/nunet-web-mode.sh rebuild
#   ./deploy/scripts/nunet-web-mode.sh status
#
# Environment (optional):
#   REPO_ROOT      Default: parent of deploy/scripts (repository root)
#   VENV_DIR       Default: $REPO_ROOT/.venv
#   PORT           Passed to gunicorn via deploy/gunicorn_conf.py (default: 8443)
#   WORKERS        Gunicorn workers (default: 1)
#   PNPM_VERSION   Default: 10.33.0

set -euo pipefail

# Avoid less(1) on TTY: long `systemctl show` lines (e.g. ExecStart) otherwise
# open a pager and the script appears hung until you press q.
export SYSTEMD_PAGER=cat

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="${REPO_ROOT:-$(cd "$SCRIPT_DIR/../.." && pwd)}"
BACKEND_DIR="$REPO_ROOT/backend"
FRONTEND_DIR="$REPO_ROOT/frontend"
FRONTEND_DIST="$FRONTEND_DIR/dist"
REQ_FILE="$BACKEND_DIR/nunet_api/requirements.txt"

VENV_DIR="${VENV_DIR:-$REPO_ROOT/.venv}"
VENV_PY="$VENV_DIR/bin/python"

# Prefer packaged gunicorn conf when installed; otherwise use repo copy.
if [[ -f /usr/lib/nunet-appliance-web/gunicorn_conf.py ]]; then
  GUNICORN_CONF="/usr/lib/nunet-appliance-web/gunicorn_conf.py"
else
  GUNICORN_CONF="$REPO_ROOT/deploy/gunicorn_conf.py"
fi

PORT="${PORT:-8443}"
WORKERS="${WORKERS:-1}"
PNPM_VERSION="${PNPM_VERSION:-10.33.0}"

# Try common unit names (historical typo vs packaged name).
SERVICE_CANDIDATES=(
  "nunet-applinace-web.service"
  "nunet-appliance-web.service"
)

active_service=""

# Use LoadState, not grep on list-unit-files: with pipefail, grep -Fxq can exit
# early and SIGPIPE the upstream pipe, making the pipeline status non-zero.
unit_file_exists() {
  local name="$1"
  local state
  state="$(systemctl show -p LoadState --value "$name" 2>/dev/null || true)"
  [[ "$state" == "loaded" ]]
}

pick_service() {
  local s
  for s in "${SERVICE_CANDIDATES[@]}"; do
    if unit_file_exists "$s"; then
      active_service="$s"
      return 0
    fi
  done
  echo "ERROR: Could not find systemd service. Checked: ${SERVICE_CANDIDATES[*]}" >&2
  exit 1
}

dropin_dir() { echo "/etc/systemd/system/${active_service}.d"; }
dropin_file() { echo "$(dropin_dir)/override.conf"; }

require_repo() {
  [[ -e "$REPO_ROOT/.git" ]] || { echo "ERROR: Not a git clone/worktree at $REPO_ROOT" >&2; exit 1; }
  [[ -f "$BACKEND_DIR/nunet_api/main.py" ]] || { echo "ERROR: Missing $BACKEND_DIR/nunet_api/main.py" >&2; exit 1; }
  [[ -f "$REQ_FILE" ]] || { echo "ERROR: Missing $REQ_FILE" >&2; exit 1; }
  [[ -f "$FRONTEND_DIR/package.json" ]] || { echo "ERROR: Missing $FRONTEND_DIR/package.json" >&2; exit 1; }
}

ensure_prereqs() {
  command -v python3 >/dev/null || { echo "ERROR: python3 not found" >&2; exit 1; }
  command -v corepack >/dev/null || { echo "ERROR: corepack not found" >&2; exit 1; }
  command -v systemctl >/dev/null || { echo "ERROR: systemctl not found" >&2; exit 1; }
}

setup_venv() {
  echo "==> Creating/updating venv at $VENV_DIR"
  python3 -m venv "$VENV_DIR"
  "$VENV_PY" -m pip install --upgrade pip wheel
  "$VENV_PY" -m pip install -r "$REQ_FILE"
  "$VENV_PY" -m pip install gunicorn
}

build_frontend() {
  echo "==> Building frontend"
  (
    cd "$FRONTEND_DIR"
    corepack prepare "pnpm@${PNPM_VERSION}" --activate
    corepack pnpm install --frozen-lockfile
    corepack pnpm run build
  )
  [[ -f "$FRONTEND_DIST/index.html" ]] || {
    echo "ERROR: Frontend build did not produce $FRONTEND_DIST/index.html" >&2
    exit 1
  }
}

write_override() {
  echo "==> Writing systemd override $(dropin_file)"
  sudo mkdir -p "$(dropin_dir)"
  sudo tee "$(dropin_file)" >/dev/null <<EOF
[Service]
WorkingDirectory=${BACKEND_DIR}
Environment=PYTHONPATH=${BACKEND_DIR}
Environment=PORT=${PORT}
Environment=WORKERS=${WORKERS}
Environment=NUNET_STATIC_DIR=${FRONTEND_DIST}

ExecStart=
ExecStart=${VENV_PY} -m gunicorn -k uvicorn.workers.UvicornWorker -c ${GUNICORN_CONF} nunet_api.main:app
EOF
}

remove_override() {
  if [[ -f "$(dropin_file)" ]]; then
    echo "==> Removing $(dropin_file)"
    sudo rm -f "$(dropin_file)"
  else
    echo "==> No override file at $(dropin_file); nothing to remove"
  fi
}

restart_service() {
  echo "==> systemctl daemon-reload && restart $active_service"
  sudo systemctl daemon-reload
  sudo systemctl restart "$active_service"
}

show_status() {
  echo
  echo "=== STATUS ==="
  echo "Service: $active_service"
  systemctl is-active "$active_service" || true
  echo
  systemctl show -p FragmentPath -p DropInPaths "$active_service"
  echo
  systemctl show -p ExecStart "$active_service"
  echo
  systemctl show -p Environment "$active_service"
}

dev_on() {
  require_repo
  ensure_prereqs
  setup_venv
  build_frontend
  write_override
  restart_service
  echo "DEV-ON: repo backend (venv) + $FRONTEND_DIST via systemd override."
  show_status
}

dev_off() {
  ensure_prereqs
  remove_override
  restart_service
  echo "DEV-OFF: override removed; service uses packaged unit defaults."
  show_status
}

rebuild() {
  require_repo
  ensure_prereqs
  setup_venv
  build_frontend
  restart_service
  echo "Rebuild: venv + frontend dist refreshed, service restarted."
  show_status
}

usage() {
  cat <<USAGE
NuNet appliance web: switch systemd service between packaged and repo-backed mode.

Usage:
  $0 dev-on     Create venv, install deps, build frontend, write override, restart
  $0 dev-off    Remove override, restart (back to packaged ExecStart)
  $0 rebuild    Refresh venv + frontend build + restart (while override active)
  $0 status     Show service unit paths, ExecStart, and Environment

Optional env: REPO_ROOT VENV_DIR PORT WORKERS PNPM_VERSION
USAGE
}

main() {
  case "${1:-}" in
    dev-on)  pick_service; dev_on ;;
    dev-off) pick_service; dev_off ;;
    rebuild) pick_service; rebuild ;;
    status)  pick_service; show_status ;;
    -h|--help|help) usage ;;
    *) usage; exit 1 ;;
  esac
}

main "$@"
