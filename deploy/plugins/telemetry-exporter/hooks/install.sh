#!/usr/bin/env bash
set -euo pipefail

# Root hook: install or upgrade Alloy package and service drop-in.
# Intentionally does not overwrite active config; config is applied by apply.sh.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
DEFAULT_CONFIG="${PLUGIN_DIR}/default-config.json"
CONFIG_PATH="${1:-/home/ubuntu/nunet/appliance/plugins/telemetry-exporter/config.json}"
STATE_DIR="/var/lib/nunet-appliance/plugins/telemetry-exporter"
LOG_DIR="/var/log/nunet-appliance/plugins/telemetry-exporter"

mkdir -p "${STATE_DIR}" "${LOG_DIR}"

if [ ! -f "${CONFIG_PATH}" ]; then
  mkdir -p "$(dirname "${CONFIG_PATH}")"
  cp "${DEFAULT_CONFIG}" "${CONFIG_PATH}"
fi

read_config() {
  local key="$1"
  python3 - "${CONFIG_PATH}" "${key}" <<'PY'
import json, sys
path, key = sys.argv[1], sys.argv[2]
with open(path, "r", encoding="utf-8") as f:
    data = json.load(f)
value = data.get(key, "")
if isinstance(value, bool):
    print("true" if value else "false")
elif value is None:
    print("")
else:
    print(str(value))
PY
}

GATEWAY_URL="$(read_config gateway_url)"
if [ -z "${GATEWAY_URL}" ]; then
  GATEWAY_URL="https://telemetry.orgs.nunet.network"
fi
TELEMETRY_TOKEN="$(read_config telemetry_token)"

echo "Installing telemetry-exporter plugin (Alloy package + unit drop-in)..."
echo "Gateway: ${GATEWAY_URL}" > "${STATE_DIR}/last-install.txt"

{
  if command -v apt-get >/dev/null 2>&1; then
    mkdir -p /etc/apt/keyrings
    if [ ! -f /etc/apt/keyrings/grafana.asc ]; then
      wget -q -O /etc/apt/keyrings/grafana.asc https://apt.grafana.com/gpg-full.key
      chmod 644 /etc/apt/keyrings/grafana.asc
    fi
    echo "deb [signed-by=/etc/apt/keyrings/grafana.asc] https://apt.grafana.com stable main" > /etc/apt/sources.list.d/grafana.list
    apt-get update -qq
    DEBIAN_FRONTEND=noninteractive apt-get install -y alloy
  fi

  mkdir -p /var/lib/nunet-appliance/alloy
  mkdir -p /etc/systemd/system/alloy.service.d
  cat > /etc/systemd/system/alloy.service.d/nunet-appliance.conf <<'DROPIN'
[Service]
Environment=CONFIG_FILE=/var/lib/nunet-appliance/alloy/config.alloy
ExecStart=
ExecStart=/usr/bin/alloy run $CUSTOM_ARGS --storage.path=/var/lib/alloy/data /var/lib/nunet-appliance/alloy/config.alloy
DROPIN
  systemctl daemon-reload
  systemctl enable alloy.service 2>/dev/null || true
  usermod -aG systemd-journal,adm alloy 2>/dev/null || true
} >> "${LOG_DIR}/install.log" 2>&1

date -u +"%Y-%m-%dT%H:%M:%SZ" > "${STATE_DIR}/installed-at.txt"
echo "Token set: $([ -n "${TELEMETRY_TOKEN}" ] && echo true || echo false)" >> "${STATE_DIR}/last-install.txt"
echo "ok"
