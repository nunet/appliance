#!/usr/bin/env bash
set -euo pipefail

# Resolve repository root from deploy/scripts
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
APPLIANCE_ROOT="${APPLIANCE_ROOT:-$ROOT}"
export APPLIANCE_ROOT

# Defaults (overridable via .env at repo root)
SERVICE_USER="${SERVICE_USER:-ubuntu}"
WEB_PORT="${WEB_PORT:-8443}"
VENV_DIR="${VENV_DIR:-$ROOT/.venv}"
DEV_RUN_DIR="${DEV_RUN_DIR:-$ROOT/.devctl/run}"

# State for install/rollback
STATE_DIR="${STATE_DIR:-/var/lib/nunet-appliance/devctl}"
STATE_FILE="$STATE_DIR/web_install_state"
PKG_NAME_WEBSVC="nunet-appliance-web"
SYSTEMD_WEBSVC="nunet-appliance-web.service"
PNPM_VERSION="${PNPM_VERSION:-10.34.5}"
WEB_MODE_SCRIPT="$ROOT/deploy/scripts/nunet-web-mode.sh"

setup_alias() {
  local alias_target="$ROOT/deploy/scripts/devctl.sh"
  local alias_line="alias devctl=\"$alias_target\""
  local bashrc="$HOME/.bashrc"

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

show_help() {
  cat <<EOF
NuNet Appliance Dev Controller

Usage:
  $(basename "$0") setup              Create .venv, install API (+ optional frontend) deps; no servers
  $(basename "$0") test-deps        Install OS packages for Playwright (optional, needs sudo)
  $(basename "$0") prod up          Start packaged web service via systemd
  $(basename "$0") prod down        Stop packaged web service
  $(basename "$0") build [version]    Build .deb packages (defaults to 1.0.0)
  $(basename "$0") install            Install latest built web package from dist/
  $(basename "$0") rollback           Revert to previous installed web package
  $(basename "$0") status             Show systemd web service and port $WEB_PORT
  $(basename "$0") logs               Tail packaged service logs
  $(basename "$0") -h|--help|help     Show this help

Integrated development (repo-backed web on https://localhost:$WEB_PORT):
  $WEB_MODE_SCRIPT dev-on
  $WEB_MODE_SCRIPT rebuild
  $WEB_MODE_SCRIPT status
  $WEB_MODE_SCRIPT dev-off

Unit tests (no live service required):
  ./deploy/scripts/run-pytest.sh

Environment (overridable via .env at repo root):
  VENV_DIR                   Default \$ROOT/.venv
  WEB_PORT                   Default 8443 (integrated web service)
  DEVCTL_SKIP_FRONTEND       Set to 1 to skip pnpm install during setup
  DEVCTL_INSTALL_PLAYWRIGHT  Set to 1 to run playwright install chromium during setup

Deprecated (removed):
  dev up / dev down     Use nunet-web-mode.sh dev-on and devctl setup instead

Examples:
  $(basename "$0") setup
  $(basename "$0") build 1.2.3
  $(basename "$0") install && $(basename "$0") prod up
EOF
}

deprecate_dev_commands() {
  cat <<EOF >&2
ERROR: 'dev up' and 'dev down' were removed.

For integrated development (SPA + API on https://localhost:$WEB_PORT):
  $WEB_MODE_SCRIPT dev-on
  $WEB_MODE_SCRIPT rebuild

For local venv / frontend deps only (unit pytest, no servers):
  $(basename "$0") setup

For optional Playwright OS libraries:
  $(basename "$0") test-deps

For Vite HMR only (not used for integration/E2E):
  cd frontend && corepack pnpm run dev
EOF
  exit 1
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
  WEB_PORT="${WEB_PORT:-8443}"
  VENV_DIR="${VENV_DIR:-$ROOT/.venv}"
  export NUNET_DATA_DIR="${NUNET_DATA_DIR:-/home/ubuntu/nunet}"
  export ENSEMBLES_DIR="${ENSEMBLES_DIR:-/home/ubuntu/ensembles}"
  export CONTRACTS_DIR="${CONTRACTS_DIR:-/home/ubuntu/contracts}"
  export DMS_CAP_FILE="${DMS_CAP_FILE:-/home/ubuntu/.nunet/cap/dms.cap}"
  export SERVICE_DMS_CAP_FILE="${SERVICE_DMS_CAP_FILE:-/home/nunet/.nunet/cap/dms.cap}"
  export NUNET_CONFIG_PATH="${NUNET_CONFIG_PATH:-/home/nunet/config/dms_config.json}"
  export NUNET_STATIC_DIR="${NUNET_STATIC_DIR:-$APPLIANCE_ROOT/frontend/dist}"
}

install_browser_deps() {
  local marker="$DEV_RUN_DIR/.browser_deps_installed"
  mkdir -p "$DEV_RUN_DIR"
  if [ -f "$marker" ]; then
    echo "Browser OS deps already installed (marker: $marker)"
    return 0
  fi

  echo "Installing browser runtime dependencies for Playwright..."
  sudo apt-get update
  sudo apt-get install -y \
    xvfb \
    chromium-browser \
    libnss3 libnspr4 \
    libatk1.0-0 libatk-bridge2.0-0 \
    libcups2 libdrm2 libgbm1 libxkbcommon0 \
    libxdamage1 libxfixes3 libxrandr2 \
    libpango-1.0-0 libasound2t64 \
    libgtk-3-0 \
    fonts-liberation ca-certificates

  touch "$marker"
  echo "Browser OS deps installed."
}

current_installed_version() {
  dpkg-query -W -f='${Version}\n' "$PKG_NAME_WEBSVC" 2>/dev/null || true
}

latest_built_deb_path() {
  ls -1t "$ROOT/dist/${PKG_NAME_WEBSVC}_"*.deb 2>/dev/null | head -n 1 || true
}

extract_version_from_deb() {
  local deb="$1"
  local base
  base="$(basename -- "$deb")"
  base="${base#${PKG_NAME_WEBSVC}_}"
  echo "${base%_*}" | sed 's/\.deb$//'
}

dropin_override_path() {
  local dropin="/etc/systemd/system/${SYSTEMD_WEBSVC}.d/override.conf"
  if [ -f "$dropin" ]; then
    echo "$dropin"
  fi
}

port_info() {
  local port="$1"
  local line
  line=$(ss -ltnp 2>/dev/null | awk -v p=":$port" '$4 ~ p {print $0; exit}')
  if [ -z "$line" ]; then
    echo "port $port: (free)"
    return 0
  fi
  local proc
  proc=$(echo "$line" | sed -n 's/.*users:(\(.*\)).*/\1/p')
  local tag=""
  if echo "$proc" | grep -q "$ROOT/.venv"; then tag="[repo-venv]"; fi
  if echo "$proc" | grep -q "/usr/lib/nunet-appliance-web"; then tag="[packaged]"; fi
  echo "port $port: $proc $tag"
}

status() {
  local svc_state svc_pid cur_ver override
  svc_state=$(systemctl is-active "$SYSTEMD_WEBSVC" 2>/dev/null || true)
  svc_pid=$(systemctl show -p MainPID --value "$SYSTEMD_WEBSVC" 2>/dev/null || echo "0")
  cur_ver=$(current_installed_version)
  override=$(dropin_override_path || true)

  echo "=== Web service (systemd) ==="
  echo "service: $SYSTEMD_WEBSVC -> ${svc_state:-unknown}${svc_pid:+ (pid:$svc_pid)}"
  echo "installed package: ${cur_ver:-none}"
  if [ -n "$override" ]; then
    echo "dev-on override: $override (repo-backed ExecStart)"
    echo "Tip: $WEB_MODE_SCRIPT status"
  else
    echo "dev-on override: none (packaged unit defaults)"
  fi
  echo
  echo "=== Integrated web port ==="
  port_info "$WEB_PORT"
  echo
  echo "venv: ${VENV_DIR} $([ -x "$VENV_DIR/bin/python" ] && echo '(present)' || echo '(missing — run: devctl setup)')"
}

prod_up() {
  sudo systemctl enable "$SYSTEMD_WEBSVC" >/dev/null 2>&1 || true
  sudo systemctl restart "$SYSTEMD_WEBSVC"
  echo "prod up: $SYSTEMD_WEBSVC started"
}

prod_down() {
  sudo systemctl stop "$SYSTEMD_WEBSVC" || true
  echo "prod down: $SYSTEMD_WEBSVC stopped"
}

setup() {
  setup_alias
  need python3
  need corepack

  if ! command -v node >/dev/null 2>&1 || ! node --version | grep -qE "v(22|24)"; then
    echo "Installing Node.js 22+ for frontend tooling..."
    curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
    sudo apt-get install -y nodejs
  fi

  corepack prepare "pnpm@${PNPM_VERSION}" --activate
  corepack pnpm --version >/dev/null 2>&1 || { echo "pnpm unavailable via corepack" >&2; exit 1; }

  if [ "${DEVCTL_SKIP_FRONTEND:-0}" != "1" ]; then
    echo "==> Installing frontend dependencies"
    (
      cd "$ROOT/frontend"
      corepack pnpm install --frozen-lockfile
      if [ "${DEVCTL_INSTALL_PLAYWRIGHT:-0}" = "1" ]; then
        corepack pnpm exec playwright install chromium \
          || echo "Skipping Playwright browser download (offline or already installed)"
      fi
    )
  else
    echo "Skipping frontend install (DEVCTL_SKIP_FRONTEND=1)"
  fi

  echo "==> Creating Python venv at $VENV_DIR"
  python3 -m venv "$VENV_DIR" 2>/dev/null || python -m venv "$VENV_DIR"
  # shellcheck disable=SC1090
  . "$VENV_DIR/bin/activate"
  pip install -U pip wheel
  pip install -r "$ROOT/backend/nunet_api/requirements.txt"
  if [ -f "$ROOT/backend/requirements-test.txt" ]; then
    pip install -r "$ROOT/backend/requirements-test.txt"
  fi

  echo "setup: complete (no servers started)"
  echo "  Unit tests:  ./deploy/scripts/run-pytest.sh"
  echo "  DEV ON:      $WEB_MODE_SCRIPT dev-on && $WEB_MODE_SCRIPT rebuild"
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

  if [ -n "$cur_ver" ]; then
    echo "previous_version=$cur_ver" | sudo tee "$STATE_FILE" >/dev/null
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

case "${1:-}" in
  ""|-h|--help|help)
    show_help ;;
  setup)
    load_env; apply_default_env; setup ;;
  test-deps)
    load_env; apply_default_env; install_browser_deps ;;
  dev)
    load_env; apply_default_env
    case "${2:-}" in
      up|down) deprecate_dev_commands ;;
      *) echo "Usage: deprecated — see: $(basename "$0") help"; deprecate_dev_commands ;;
    esac
    ;;
  prod)
    load_env; apply_default_env
    case "${2:-}" in up) prod_up ;; down) prod_down ;; *) echo "Usage: $0 prod [up|down]"; exit 1 ;; esac
    ;;
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
  *)
    show_help ; exit 1 ;;
esac
