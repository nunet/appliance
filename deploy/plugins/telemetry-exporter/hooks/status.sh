#!/usr/bin/env bash
set -euo pipefail

# Root hook: machine-readable plugin runtime status.
# Prints one JSON object to stdout.

CONFIG_PATH="${1:-/home/ubuntu/nunet/appliance/plugins/telemetry-exporter/config.json}"

json_get() {
  local key="$1"
  if [ ! -f "${CONFIG_PATH}" ]; then
    echo ""
    return 0
  fi
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

ENABLED="$(json_get enabled)"
REMOTE_ENABLED="$(json_get remote_enabled)"
LOCAL_ENABLED="$(json_get local_enabled)"
DCGM_ENABLED="$(json_get dcgm_exporter_enabled)"
GRAFANA_ENABLED="$(json_get grafana_enabled)"
GATEWAY_URL="$(json_get gateway_url)"
TOKEN="$(json_get telemetry_token)"
TOKEN_SET="false"
if [ -n "${TOKEN}" ]; then
  TOKEN_SET="true"
fi

ALLOY_INSTALLED="false"
if [ -x /usr/bin/alloy ]; then
  ALLOY_INSTALLED="true"
fi

ALLOY_RUNNING="false"
if systemctl is-active --quiet alloy; then
  ALLOY_RUNNING="true"
fi

LOCAL_MIMIR_RUNNING="false"
if command -v docker >/dev/null 2>&1; then
  if docker inspect -f '{{.State.Running}}' mimir-appliance 2>/dev/null | grep -q '^true$'; then
    LOCAL_MIMIR_RUNNING="true"
  fi
fi

detect_nvidia_gpu() {
  local smi_cmd=""
  if command -v nvidia-smi >/dev/null 2>&1; then
    smi_cmd="$(command -v nvidia-smi)"
  elif [ -x /usr/lib/wsl/lib/nvidia-smi ]; then
    smi_cmd="/usr/lib/wsl/lib/nvidia-smi"
  fi
  if [ -n "${smi_cmd}" ]; then
    if "${smi_cmd}" -L >/dev/null 2>&1; then
      return 0
    fi
  fi
  # WSL GPU virtualization device.
  if [ -e /dev/dxg ]; then
    return 0
  fi
  if [ -d /proc/driver/nvidia/gpus ] && [ -n "$(ls -A /proc/driver/nvidia/gpus 2>/dev/null)" ]; then
    return 0
  fi
  if [ -c /dev/nvidiactl ] || [ -c /dev/nvidia0 ]; then
    return 0
  fi
  if command -v nvidia-container-cli >/dev/null 2>&1; then
    if nvidia-container-cli -k -d /dev/null info >/dev/null 2>&1; then
      return 0
    fi
  fi
  if command -v lspci >/dev/null 2>&1; then
    if lspci 2>/dev/null | awk '{print tolower($0)}' | awk '/nvidia/ && (/vga/ || /3d controller/ || /display controller/) { found=1 } END { exit(found ? 0 : 1) }'; then
      return 0
    fi
  fi
  return 1
}

NVIDIA_GPU_AVAILABLE="false"
if detect_nvidia_gpu; then
  NVIDIA_GPU_AVAILABLE="true"
fi

DCGM_EXPORTER_RUNNING="false"
if command -v docker >/dev/null 2>&1; then
  if docker inspect -f '{{.State.Running}}' dcgm-exporter-appliance 2>/dev/null | grep -q '^true$'; then
    DCGM_EXPORTER_RUNNING="true"
  fi
fi

CADVISOR_RUNNING="false"
if command -v docker >/dev/null 2>&1; then
  if docker inspect -f '{{.State.Running}}' cadvisor-appliance 2>/dev/null | grep -q '^true$'; then
    CADVISOR_RUNNING="true"
  fi
fi

LOCAL_GRAFANA_RUNNING="false"
if command -v docker >/dev/null 2>&1; then
  if docker inspect -f '{{.State.Running}}' grafana-appliance 2>/dev/null | grep -q '^true$'; then
    LOCAL_GRAFANA_RUNNING="true"
  fi
fi

cat <<EOF
{
  "plugin_id": "telemetry-exporter",
  "enabled": ${ENABLED:-false},
  "remote_enabled": ${REMOTE_ENABLED:-false},
  "local_enabled": ${LOCAL_ENABLED:-false},
  "dcgm_exporter_enabled": ${DCGM_ENABLED:-false},
  "grafana_enabled": ${GRAFANA_ENABLED:-false},
  "nvidia_gpu_available": ${NVIDIA_GPU_AVAILABLE},
  "gateway_url": "${GATEWAY_URL:-https://telemetry.orgs.nunet.network}",
  "token_set": ${TOKEN_SET},
  "alloy_installed": ${ALLOY_INSTALLED},
  "alloy_running": ${ALLOY_RUNNING},
  "local_mimir_running": ${LOCAL_MIMIR_RUNNING},
  "dcgm_exporter_running": ${DCGM_EXPORTER_RUNNING},
  "cadvisor_running": ${CADVISOR_RUNNING},
  "local_grafana_running": ${LOCAL_GRAFANA_RUNNING},
  "grafana_url": "/sys/plugins/telemetry-exporter/grafana/"
}
EOF
