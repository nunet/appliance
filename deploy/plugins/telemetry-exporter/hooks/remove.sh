#!/usr/bin/env bash
set -euo pipefail

# Root hook: disable telemetry-exporter plugin resources.
# Removes telemetry exporter services/config and local telemetry data.
# Set PURGE_ALLOY=1 to remove the Alloy package too.

STATE_DIR="/var/lib/nunet-appliance/plugins/telemetry-exporter"
LOG_DIR="/var/log/nunet-appliance/plugins/telemetry-exporter"
PURGE_ALLOY="${PURGE_ALLOY:-0}"
CONFIG_PATH="/home/ubuntu/nunet/appliance/plugins/telemetry-exporter/config.json"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
COMPOSE_FILE="${PLUGIN_DIR}/compose.yaml"
COMPOSE_PROJECT="nunet-telemetry"

mkdir -p "${STATE_DIR}" "${LOG_DIR}"

docker rm -f mimir-appliance dcgm-exporter-appliance cadvisor-appliance grafana-appliance 2>/dev/null || true
docker compose -f "${COMPOSE_FILE}" -p "${COMPOSE_PROJECT}" down -v 2>/dev/null || true

systemctl stop alloy 2>/dev/null || true
systemctl disable alloy 2>/dev/null || true

rm -f /etc/systemd/system/alloy.service.d/nunet-appliance.conf 2>/dev/null || true
systemctl daemon-reload || true

rm -f /var/lib/nunet-appliance/alloy/config.alloy 2>/dev/null || true
rm -rf /var/lib/nunet-appliance/mimir 2>/dev/null || true
# Legacy cleanup path from earlier bind-mount based Grafana data.
rm -rf /var/lib/nunet-appliance/grafana 2>/dev/null || true
rm -f "${CONFIG_PATH}" 2>/dev/null || true

if [ "${PURGE_ALLOY}" = "1" ] && command -v apt-get >/dev/null 2>&1; then
  DEBIAN_FRONTEND=noninteractive apt-get remove -y alloy >> "${LOG_DIR}/remove.log" 2>&1 || true
fi

date -u +"%Y-%m-%dT%H:%M:%SZ" > "${STATE_DIR}/removed-at.txt"
echo "removed"
