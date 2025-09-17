#!/usr/bin/env bash
set -euo pipefail

# Resolve repository root from deploy/scripts
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Self-setup: Ensure devctl alias exists and points to absolute path
setup_alias() {
  local alias_target="$ROOT/deploy/scripts/devctl.sh"
  local alias_line="alias devctl=\"$alias_target\""
  local bashrc="$HOME/.bashrc"
  
  # If alias is missing, add it; if present but incorrect, replace it
  if ! grep -q "^alias devctl=" "$bashrc" 2>/dev/null; then
    echo "🔧 Setting up devctl alias..."
    echo "$alias_line" >> "$bashrc"
    echo "✅ Alias added to ~/.bashrc"
    echo "💡 Run 'source ~/.bashrc' or start a new terminal to use 'devctl' from anywhere"
  else
    # Ensure it points to our absolute path
    if ! grep -q "^$(printf %q "${alias_line}")$" "$bashrc" 2>/dev/null; then
      # Replace existing devctl alias line with the correct absolute path
      sed -i "s|^alias devctl=.*$|${alias_line}|" "$bashrc"
      echo "🔄 Updated existing devctl alias to: $alias_target"
    fi
  fi
}

# Run alias setup on first use
setup_alias

# Defaults (overridable via .env.dev)
SERVICE_USER="${SERVICE_USER:-ubuntu}"
BACKEND_PORT="${BACKEND_PORT:-8080}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"
CORS_ORIGINS="${CORS_ORIGINS:-http://localhost:${FRONTEND_PORT}}"
VENV_DIR="${VENV_DIR:-$ROOT/deploy/.dev-venv}"
TMUX_SESSION="nunet-dev"

# State for install/rollback
STATE_DIR="${STATE_DIR:-/var/lib/nunet-appliance/devctl}"
STATE_FILE="$STATE_DIR/web_install_state"
PKG_NAME_WEBSVC="nunet-appliance-web"
SYSTEMD_WEBSVC="nunet-appliance-web.service"

load_env() {
  [ -f "$ROOT/.env.dev" ] && set -a && . "$ROOT/.env.dev" && set +a || true
}

need() { command -v "$1" >/dev/null 2>&1 || { echo "Missing dependency: $1" >&2; exit 1; }; }

ensure_state_dir() {
  sudo mkdir -p "$STATE_DIR"
  sudo chmod 0775 "$STATE_DIR" || true
}

current_installed_version() {
  dpkg-query -W -f='${Version}\n' "$PKG_NAME_WEBSVC" 2>/dev/null || true
}

latest_built_deb_path() {
  ls -1t "$ROOT/dist/${PKG_NAME_WEBSVC}_"*.deb 2>/dev/null | head -n 1 || true
}

extract_version_from_deb() {
  # deb filename format: name_version_arch.deb
  local deb="$1"
  local base
  base="$(basename -- "$deb")"
  # strip prefix
  base="${base#${PKG_NAME_WEBSVC}_}"
  # remove arch suffix
  echo "${base%_*}" | sed 's/\.deb$//' # returns version
}

status() {
  echo "Systemd services:"
  systemctl is-active "$SYSTEMD_WEBSVC" || true
  echo
  echo "Dev processes:"
  pgrep -a node | grep "$ROOT/frontend" || true
  pgrep -a python | grep "$ROOT/backend" || true
  echo
  echo "Ports:"
  ss -ltnp | grep -E ":($BACKEND_PORT|$FRONTEND_PORT)\\b" || true
}

prod_up() {
  dev_down || true
  sudo systemctl enable "$SYSTEMD_WEBSVC" >/dev/null 2>&1 || true
  sudo systemctl restart "$SYSTEMD_WEBSVC"
  echo "prod up: $SYSTEMD_WEBSVC started"
}

prod_down() {
  sudo systemctl stop "$SYSTEMD_WEBSVC" || true
  echo "prod down: $SYSTEMD_WEBSVC stopped"
}

dev_setup() {
  need python3; need tmux
  
  # Check Node.js version and install if needed
  if ! command -v node >/dev/null 2>&1 || ! node --version | grep -qE "v(20|22)"; then
    echo "Installing Node.js 20+ for frontend development..."
    curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
    sudo apt-get install -y nodejs
  fi
  
  need npm
  python3 -m venv "$VENV_DIR" 2>/dev/null || python -m venv "$VENV_DIR"
  # shellcheck disable=SC1090
  . "$VENV_DIR/bin/activate"
  pip install -U pip wheel uvicorn gunicorn
  pip install -r "$ROOT/backend/nunet_api/requirements.txt"
}

dev_up() {
  prod_down || true
  dev_setup
  tmux has-session -t "$TMUX_SESSION" 2>/dev/null && tmux kill-session -t "$TMUX_SESSION" || true
  # Use bash --norc to bypass .bashrc splash screen
  tmux new-session -d -s "$TMUX_SESSION" -c "$ROOT/frontend" "bash --norc -c 'PORT=$FRONTEND_PORT npm install && PORT=$FRONTEND_PORT npm run dev'"
  tmux new-window -t "$TMUX_SESSION" -n backend -c "$ROOT/backend" \
    "bash --norc -c \"export CORS_ORIGINS='$CORS_ORIGINS'; exec uvicorn nunet_api.main:app --host 0.0.0.0 --port $BACKEND_PORT --reload\""
  echo "dev up: tmux session '$TMUX_SESSION' started (windows: frontend, backend)"
  echo "Attach with: tmux attach -t $TMUX_SESSION"
  echo "Note: Using bash --norc to bypass splash screen in dev mode"
}

dev_down() {
  tmux kill-session -t "$TMUX_SESSION" 2>/dev/null || true
  pkill -f "uvicorn .*--port $BACKEND_PORT" 2>/dev/null || true
  pkill -f "npm run dev" 2>/dev/null || true
  echo "dev down: stopped dev processes"
}

build() {
  local version="${1:-1.0.0}"
  ( cd "$ROOT/deploy/scripts" && ./build.sh "$version" )
}

install_latest() {
  ensure_state_dir

  local deb
  deb="$(latest_built_deb_path)"
  if [ -z "$deb" ]; then
    echo "No built package found in $ROOT/dist for $PKG_NAME_WEBSVC" >&2
    exit 1
  fi

  local cur_ver prev_deb new_ver
  cur_ver="$(current_installed_version)"
  new_ver="$(extract_version_from_deb "$deb")"

  if [ -n "$cur_ver" ] && [ "$cur_ver" = "$new_ver" ]; then
    echo "Already installed: $PKG_NAME_WEBSVC $cur_ver"
    return 0
  fi

  # Save rollback info
  if [ -n "$cur_ver" ]; then
    echo "previous_version=$cur_ver" | sudo tee "$STATE_FILE" >/dev/null
    # Try to locate a matching deb in dist for rollback convenience
    prev_deb="$(ls -1 "$ROOT/dist/${PKG_NAME_WEBSVC}_${cur_ver}_"*.deb 2>/dev/null | head -n1 || true)"
    [ -n "$prev_deb" ] && echo "previous_deb=$prev_deb" | sudo tee -a "$STATE_FILE" >/dev/null
  else
    sudo rm -f "$STATE_FILE" 2>/dev/null || true
  fi

  echo "Installing $deb (version $new_ver) ..."
  sudo apt install -y "$deb"
  echo "Installed $PKG_NAME_WEBSVC $new_ver"
}

rollback() {
  ensure_state_dir
  if [ ! -f "$STATE_FILE" ]; then
    echo "No rollback info found at $STATE_FILE" >&2
    exit 1
  fi

  # shellcheck disable=SC1090
  . "$STATE_FILE"
  local target_deb="${previous_deb:-}"
  local target_ver="${previous_version:-}"

  if [ -z "$target_deb" ] || [ ! -f "$target_deb" ]; then
    if [ -n "$target_ver" ]; then
      target_deb="$(ls -1 "$ROOT/dist/${PKG_NAME_WEBSVC}_${target_ver}_"*.deb 2>/dev/null | head -n1 || true)"
    fi
  fi

  if [ -z "$target_deb" ] || [ ! -f "$target_deb" ]; then
    echo "Cannot find previous package to roll back to. Looked for version '$target_ver'." >&2
    exit 1
  fi

  echo "Rolling back to $target_deb ..."
  sudo apt install -y "$target_deb"
  echo "Rollback complete."
}

logs() {
  journalctl -u "$SYSTEMD_WEBSVC" -f -n 100 --no-pager
}

doctor() {
  echo "Checking dependencies and ports..."
  for x in python3 npm tmux ss systemctl dpkg-query; do need "$x"; done
  ss -ltn | grep -E ":($BACKEND_PORT|$FRONTEND_PORT)\\b" && echo "Warning: dev ports busy" || true
  echo "OK"
}

case "${1:-}" in
  dev)
    load_env; case "${2:-}" in up) dev_up ;; down) dev_down ;; *) echo "Usage: $0 dev [up|down]"; exit 1 ;; esac ;;
  prod)
    case "${2:-}" in up) prod_up ;; down) prod_down ;; *) echo "Usage: $0 prod [up|down]"; exit 1 ;; esac ;;
  build)
    build "${2:-1.0.0}" ;;
  install)
    install_latest ;;
  rollback)
    rollback ;;
  status)
    status ;;
  logs)
    logs ;;
  ps)
    ss -ltnp | grep -E ":($BACKEND_PORT|$FRONTEND_PORT)\\b" || true ;;
  doctor)
    doctor ;;
  *)
    echo "Usage: $0 {dev up|dev down|prod up|prod down|build [ver]|install|rollback|status|logs|ps|doctor}" ; exit 1 ;;
esac


