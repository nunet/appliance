#!/usr/bin/env bash
set -euo pipefail

# Resolve repository root from deploy/scripts
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
APPLIANCE_ROOT="${APPLIANCE_ROOT:-$ROOT}"
export APPLIANCE_ROOT

# Self-setup: Ensure devctl alias exists and points to absolute path
setup_alias() {
  local alias_target="$ROOT/deploy/scripts/devctl.sh"
  local alias_line="alias devctl=\"$alias_target\""
  local bashrc="$HOME/.bashrc"

  # Ensure ~/.bashrc contains an alias pointing at this script
  if ! grep -q "^alias devctl=" "$bashrc" 2>/dev/null; then
    echo "Setting up devctl alias..."
    echo "$alias_line" >> "$bashrc"
    echo "Alias added to ~/.bashrc"
    echo "Run 'source ~/.bashrc' or start a new terminal to use 'devctl' from anywhere"
  else
    if ! grep -q "^$(printf %q "${alias_line}")$" "$bashrc" 2>/dev/null; then
      sed -i "s|^alias devctl=.*$|${alias_line}|" "$bashrc"
      echo "Updated existing devctl alias to: $alias_target"
    fi
  fi
}

# Run alias setup on first use
setup_alias

# Defaults (overridable via .env dev/prod)
SERVICE_USER="${SERVICE_USER:-ubuntu}"
BACKEND_PORT="${BACKEND_PORT:-8080}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"
CORS_ORIGINS="${CORS_ORIGINS:-http://localhost:${FRONTEND_PORT}}"
VENV_DIR="${VENV_DIR:-$ROOT/.venv}"
TMUX_SESSION="nunet-dev"
DEVCTL_USE_TMUX="${DEVCTL_USE_TMUX:-0}"
DEV_RUN_DIR="${DEV_RUN_DIR:-$ROOT/.devctl/run}"
DEV_BACKEND_PIDFILE="$DEV_RUN_DIR/backend.pid"
DEV_FRONTEND_PIDFILE="$DEV_RUN_DIR/frontend.pid"
DEV_BACKEND_LOG="$DEV_RUN_DIR/backend.log"
DEV_FRONTEND_LOG="$DEV_RUN_DIR/frontend.log"

# State for install/rollback
STATE_DIR="${STATE_DIR:-/var/lib/nunet-appliance/devctl}"
STATE_FILE="$STATE_DIR/web_install_state"
PKG_NAME_WEBSVC="nunet-appliance-web"
SYSTEMD_WEBSVC="nunet-appliance-web.service"
PNPM_VERSION="${PNPM_VERSION:-10.4.0}"

show_help() {
  cat <<EOF
NuNet Appliance Dev Controller

Usage:
  $(basename "$0") dev up              Start dev mode (frontend HMR + backend reload)
  $(basename "$0") dev down            Stop dev mode processes
  $(basename "$0") prod up             Start packaged web service via systemd
  $(basename "$0") prod down           Stop packaged web service
  $(basename "$0") build [version]     Build packages (defaults to 1.0.0)
  $(basename "$0") install             Install latest built web package from dist/
  $(basename "$0") rollback            Revert to previous installed web package
  $(basename "$0") status              Show services, dev processes, and ports
  $(basename "$0") logs                Tail packaged service logs
  $(basename "$0") ps                  Show listeners on dev ports
  $(basename "$0") doctor              Check deps and port availability
  $(basename "$0") -h|--help|help      Show this help

Environment (overridable via .env at repo root):
  SERVICE_USER     Default ubuntu
  BACKEND_PORT     Default 8080
  FRONTEND_PORT    Default 5173
  CORS_ORIGINS     Default http://localhost:5173
  VENV_DIR         Default deploy/.dev-venv under repo
  DEVCTL_USE_TMUX  Default 0 (set to 1 to use legacy tmux dev up)

Examples:
  $(basename "$0") build 1.2.3
  $(basename "$0") install && $(basename "$0") prod up
  $(basename "$0") dev up   # set DEVCTL_USE_TMUX=1 if you prefer tmux windows
EOF
}

load_env() {
  if [ -f "$ROOT/.env" ]; then
    set -a && . "$ROOT/.env" && set +a
  elif [ -f "$ROOT/.env.dev" ]; then
    set -a && . "$ROOT/.env.dev" && set +a
  fi
  set +a
}

need() { command -v "$1" >/dev/null 2>&1 || { echo "Missing dependency: $1" >&2; exit 1; }; }

ensure_state_dir() {
  sudo mkdir -p "$STATE_DIR"
  sudo chmod 0775 "$STATE_DIR" || true
}

apply_default_env() {
  APPLIANCE_ROOT="${APPLIANCE_ROOT:-$ROOT}"
  export APPLIANCE_ROOT
  BACKEND_PORT="${BACKEND_PORT:-8080}"
  FRONTEND_PORT="${FRONTEND_PORT:-5173}"
  CORS_ORIGINS="${CORS_ORIGINS:-http://localhost:${FRONTEND_PORT}}"
  VENV_DIR="${VENV_DIR:-$ROOT/.venv}"
  export NUNET_DATA_DIR="${NUNET_DATA_DIR:-/home/ubuntu/nunet}"
  export ENSEMBLES_DIR="${ENSEMBLES_DIR:-/home/ubuntu/ensembles}"
  export CONTRACTS_DIR="${CONTRACTS_DIR:-/home/ubuntu/contracts}"
  export DMS_CAP_FILE="${DMS_CAP_FILE:-/home/ubuntu/.nunet/cap/dms.cap}"
  export SERVICE_DMS_CAP_FILE="${SERVICE_DMS_CAP_FILE:-/home/nunet/.nunet/cap/dms.cap}"
  export NUNET_CONFIG_PATH="${NUNET_CONFIG_PATH:-/home/nunet/config/dms_config.json}"
  export NUNET_STATIC_DIR="${NUNET_STATIC_DIR:-$APPLIANCE_ROOT/frontend/dist}"
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
  # Helper: who owns a port and is it likely DEV or PROD
  port_info() {
    local port="$1"
    local line
    line=$(ss -ltnp 2>/dev/null | awk -v p=":$port" '$4 ~ p {print $0; exit}')
    if [ -z "$line" ]; then
      echo "port $port: (free)"
      return 0
    fi
    # Extract process command
    local proc
    proc=$(echo "$line" | sed -n 's/.*users:(\(.*\)).*/\1/p')
    # Tag as DEV or PROD based on command path hints
    local tag=""
    if echo "$proc" | grep -q "$ROOT/frontend"; then tag="[DEV:frontend]"; fi
    if echo "$proc" | grep -q "$ROOT/backend"; then tag="[DEV:backend]"; fi
    if echo "$proc" | grep -q "/usr/lib/nunet-appliance-web"; then tag="[PROD:web]"; fi
    echo "port $port: $proc $tag"
  }

  local svc_state svc_pid tmux_state cur_ver
  svc_state=$(systemctl is-active "$SYSTEMD_WEBSVC" || true)
  svc_pid=$(systemctl show -p MainPID --value "$SYSTEMD_WEBSVC" 2>/dev/null || echo "0")
  tmux_state="inactive"
  if [ "$DEVCTL_USE_TMUX" = "1" ] && command -v tmux >/dev/null 2>&1; then
    tmux has-session -t "$TMUX_SESSION" 2>/dev/null && tmux_state="active" || tmux_state="inactive"
  fi
  cur_ver=$(current_installed_version)

  echo "=== PROD (systemd) ==="
  echo "service: $SYSTEMD_WEBSVC -> $svc_state${svc_pid:+ (pid:$svc_pid)}"
  echo "installed: ${cur_ver:-none}"
  echo
  echo "=== DEV ==="
  if [ "$DEVCTL_USE_TMUX" = "1" ]; then
    echo "session: $TMUX_SESSION -> $tmux_state"
    if [ "$tmux_state" = "active" ]; then
      tmux list-windows -t "$TMUX_SESSION" 2>/dev/null | sed 's/^/  window: /'
    fi
  else
    if [ -f "$DEV_BACKEND_PIDFILE" ]; then
      echo "backend pid: $(cat "$DEV_BACKEND_PIDFILE") (log: $DEV_BACKEND_LOG)"
    else
      echo "backend pid: <none>"
    fi
    if [ -f "$DEV_FRONTEND_PIDFILE" ]; then
      echo "frontend pid: $(cat "$DEV_FRONTEND_PIDFILE") (log: $DEV_FRONTEND_LOG)"
    else
      echo "frontend pid: <none>"
    fi
  fi
  echo
  echo "=== Ports ==="
  port_info "$BACKEND_PORT"
  port_info "$FRONTEND_PORT"
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
  need python3
  need corepack

  # Check Node.js version and install if needed
  if ! command -v node >/dev/null 2>&1 || ! node --version | grep -qE "v(22|24)"; then
    echo "Installing Node.js 22+ for frontend development..."
    curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
    sudo apt-get install -y nodejs
  fi

  corepack prepare "pnpm@${PNPM_VERSION}" --activate
  corepack pnpm --version >/dev/null 2>&1 || { echo "pnpm unavailable via corepack"; exit 1; }
  python3 -m venv "$VENV_DIR" 2>/dev/null || python -m venv "$VENV_DIR"
  # shellcheck disable=SC1090
  . "$VENV_DIR/bin/activate"
  pip install -U pip wheel
  pip install -r "$ROOT/backend/nunet_api/requirements.txt"
}

start_dev_processes() {
  mkdir -p "$DEV_RUN_DIR"
  bash "$ROOT/deploy/scripts/dev_frontend.sh" >"$DEV_FRONTEND_LOG" 2>&1 &
  echo $! > "$DEV_FRONTEND_PIDFILE"
  bash "$ROOT/deploy/scripts/dev_backend.sh" >"$DEV_BACKEND_LOG" 2>&1 &
  echo $! > "$DEV_BACKEND_PIDFILE"
  echo "dev up: started frontend (pid $(cat "$DEV_FRONTEND_PIDFILE")) and backend (pid $(cat "$DEV_BACKEND_PIDFILE"))"
  echo "logs: $DEV_FRONTEND_LOG, $DEV_BACKEND_LOG"
}

stop_pidfile() {
  local pidfile="$1"
  if [ -f "$pidfile" ]; then
    local pid
    pid=$(cat "$pidfile" 2>/dev/null || true)
    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
    fi
    rm -f "$pidfile"
  fi
}

dev_up_tmux() {
  tmux has-session -t "$TMUX_SESSION" 2>/dev/null && tmux kill-session -t "$TMUX_SESSION" || true
  tmux new-session -d -s "$TMUX_SESSION" -c "$ROOT/frontend" "bash --norc -c 'PORT=$FRONTEND_PORT corepack pnpm install --frozen-lockfile && PORT=$FRONTEND_PORT corepack pnpm run dev'"
  tmux new-window -t "$TMUX_SESSION" -n backend -c "$ROOT/backend" \
    "bash --norc -c \"export CORS_ORIGINS='$CORS_ORIGINS'; exec gunicorn -k uvicorn.workers.UvicornWorker nunet_api.main:app --bind 0.0.0.0:$BACKEND_PORT --reload --workers 1\""
  echo "dev up: tmux session '$TMUX_SESSION' started (windows: frontend, backend)"
  echo "Attach with: tmux attach -t $TMUX_SESSION"
}

dev_up() {
  prod_down || true
  dev_setup
  if [ "$DEVCTL_USE_TMUX" = "1" ]; then
    dev_up_tmux
  else
    start_dev_processes
  fi
}

dev_down() {
  if [ "$DEVCTL_USE_TMUX" = "1" ]; then
    tmux kill-session -t "$TMUX_SESSION" 2>/dev/null || true
  fi
  stop_pidfile "$DEV_BACKEND_PIDFILE"
  stop_pidfile "$DEV_FRONTEND_PIDFILE"
  pkill -f "gunicorn .*--bind 0.0.0.0:$BACKEND_PORT" 2>/dev/null || true
  pkill -f "uvicorn .*--port $BACKEND_PORT" 2>/dev/null || true
  pkill -f "pnpm run dev" 2>/dev/null || true
  pkill -f "vite" 2>/dev/null || true
  if command -v fuser >/dev/null 2>&1; then
    fuser -k "${FRONTEND_PORT}/tcp" 2>/dev/null || true
  fi
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
  for x in python3 corepack ss systemctl dpkg-query; do need "$x"; done
  if [ "$DEVCTL_USE_TMUX" = "1" ]; then need tmux; fi
  ss -ltn | grep -E ":($BACKEND_PORT|$FRONTEND_PORT)\\b" && echo "Warning: dev ports busy" || true
  echo "OK"
}

case "${1:-}" in
  ""|-h|--help|help)
    show_help ;;
  dev)
    load_env; apply_default_env; case "${2:-}" in up) dev_up ;; down) dev_down ;; *) echo "Usage: $0 dev [up|down]"; exit 1 ;; esac ;;
  prod)
    load_env; apply_default_env; case "${2:-}" in up) prod_up ;; down) prod_down ;; *) echo "Usage: $0 prod [up|down]"; exit 1 ;; esac ;;
  build)
    load_env; apply_default_env; build "${2:-1.0.0}" ;;
  install)
    load_env; apply_default_env; install_latest ;;
  rollback)
    load_env; apply_default_env; rollback ;;
  status)
    load_env; apply_default_env; status ;;
  logs)
    load_env; apply_default_env; logs ;;
  ps)
    load_env; apply_default_env; ss -ltnp | grep -E ":($BACKEND_PORT|$FRONTEND_PORT)\\b" || true ;;
  doctor)
    load_env; apply_default_env; doctor ;;
  *)
    show_help ; exit 1 ;;
esac
