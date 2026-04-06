#!/usr/bin/env bash
set -euo pipefail

# Root hook: apply generated Alloy config and manage local collectors.
# Contract:
#   apply.sh [CONFIG_JSON_PATH] [DID] [PEER_ID]
# Config keys:
#   enabled (bool)
#   remote_enabled (bool)
#   local_enabled (bool)
#   dcgm_exporter_enabled (bool)
#   grafana_enabled (bool)
#   generated_config_path (string)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
DEFAULT_CONFIG="${PLUGIN_DIR}/default-config.json"
CONFIG_PATH="${1:-/home/ubuntu/nunet/appliance/plugins/telemetry-exporter/config.json}"
DID_RAW="${2:-}"
PEER_ID_RAW="${3:-}"
STATE_DIR="/var/lib/nunet-appliance/plugins/telemetry-exporter"
LOG_DIR="/var/log/nunet-appliance/plugins/telemetry-exporter"
COMPOSE_FILE="${PLUGIN_DIR}/compose.yaml"
COMPOSE_PROJECT="nunet-telemetry"

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

has_nvidia_gpu() {
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

ensure_alloy_service_override() {
  mkdir -p /etc/systemd/system/alloy.service.d
  cat > /etc/systemd/system/alloy.service.d/nunet-appliance.conf <<'DROPIN'
[Service]
Environment=CONFIG_FILE=/var/lib/nunet-appliance/alloy/config.alloy
ExecStart=
ExecStart=/usr/bin/alloy run $CUSTOM_ARGS --storage.path=/var/lib/alloy/data /var/lib/nunet-appliance/alloy/config.alloy
DROPIN
  systemctl daemon-reload
}

sanitize_label_value() {
  local raw="${1:-}"
  printf '%s' "${raw}" | tr -d '\n\r' | head -c 256
}

alloy_quote() {
  local v
  v="$(sanitize_label_value "${1:-}")"
  v="${v//\\/\\\\}"
  v="${v//\"/\\\"}"
  printf '"%s"' "${v}"
}

ensure_mimir_config() {
  mkdir -p /var/lib/nunet-appliance/mimir/data
  cat > /var/lib/nunet-appliance/mimir/mimir.yaml <<'MIMIR_CFG'
multitenancy_enabled: false
server:
  http_listen_port: 9009
common:
  storage:
    backend: filesystem
    filesystem:
      dir: /data
blocks_storage:
  backend: filesystem
  filesystem:
    dir: /data/blocks
ruler_storage:
  backend: local
  local:
    directory: /data/rules
ingester:
  ring:
    kvstore:
      store: inmemory
    replication_factor: 1
distributor:
  ring:
    kvstore:
      store: inmemory
MIMIR_CFG
}

ensure_grafana_dashboards() {
  local target_dir="/var/lib/nunet-appliance/grafana/dashboards"
  local bundled_dir="${PLUGIN_DIR}/grafana/dashboards"
  mkdir -p "${target_dir}"

  # Best-effort: pull official Grafana dashboards and rewrite datasource -> local_mimir.
  python3 - "${target_dir}" <<'PY'
import json
import urllib.request
from pathlib import Path

target_dir = Path(__import__("sys").argv[1])
target_dir.mkdir(parents=True, exist_ok=True)

dashboards = [
    # Grafana.com official/community dashboards used in many installations.
    ("node_exporter.json", 1860, 37),
    ("cadvisor_allocations.json", 14282, 1),
    ("dcgm_exporter.json", 12239, 1),
]

def rewrite_datasource(obj):
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if k == "datasource":
                out[k] = {"type": "prometheus", "uid": "local_mimir"}
            elif k == "__inputs":
                out[k] = []
            else:
                out[k] = rewrite_datasource(v)
        return out
    if isinstance(obj, list):
        return [rewrite_datasource(i) for i in obj]
    return obj

def patch_cadvisor_for_appliance(obj):
    # Normalize dashboard queries to use `name` label.
    # Some imported revisions use `id`; cadvisor:latest exposes richer name labels.
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if k == "expr" and isinstance(v, str):
                nv = v
                nv = nv.replace('id=~"$container",id=~".+"', 'name=~"$container",name=~".+"')
                nv = nv.replace('id=~"$container"', 'name=~"$container"')
                nv = nv.replace(" by (id)", " by (name)")
                out[k] = nv
            elif k == "legendFormat" and isinstance(v, str):
                out[k] = v.replace("{{id}}", "{{name}}")
            elif k in ("definition",) and isinstance(v, str):
                out[k] = v.replace(",id)", ",name)")
            elif k == "query" and isinstance(v, dict):
                q = dict(v)
                qv = q.get("query")
                if isinstance(qv, str):
                    q["query"] = qv.replace(",id)", ",name)")
                out[k] = patch_cadvisor_for_appliance(q)
            else:
                out[k] = patch_cadvisor_for_appliance(v)
        return out
    if isinstance(obj, list):
        return [patch_cadvisor_for_appliance(i) for i in obj]
    return obj

for filename, dash_id, revision in dashboards:
    url = f"https://grafana.com/api/dashboards/{dash_id}/revisions/{revision}/download"
    out_path = target_dir / filename
    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            raw = resp.read().decode("utf-8")
        payload = json.loads(raw)
        payload = rewrite_datasource(payload)
        if filename == "cadvisor_allocations.json":
            payload = patch_cadvisor_for_appliance(payload)
        out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except Exception:
        # Keep existing file if present; fallback copied by shell below.
        pass
PY

  # Fallback/canonical files to guarantee dashboards always exist.
  [ -f "${target_dir}/node_exporter.json" ] || cp -f "${bundled_dir}/node_exporter.json" "${target_dir}/node_exporter.json"
  [ -f "${target_dir}/cadvisor_allocations.json" ] || cp -f "${bundled_dir}/cadvisor_allocations.json" "${target_dir}/cadvisor_allocations.json"
  [ -f "${target_dir}/dcgm_exporter.json" ] || cp -f "${bundled_dir}/dcgm_exporter.json" "${target_dir}/dcgm_exporter.json"
  cp -f "${bundled_dir}/nunet_pro_overview.json" "${target_dir}/nunet_pro_overview.json"
}

ENABLED="$(read_config enabled)"
REMOTE_ENABLED="$(read_config remote_enabled)"
LOCAL_ENABLED="$(read_config local_enabled)"
DCGM_ENABLED="$(read_config dcgm_exporter_enabled)"
GRAFANA_ENABLED="$(read_config grafana_enabled)"
GENERATED_CONFIG_PATH="$(read_config generated_config_path)"
GATEWAY_URL="$(read_config gateway_url)"
TOKEN="$(read_config telemetry_token)"
DID_LABEL="$(sanitize_label_value "${DID_RAW}")"
PEER_ID_LABEL="$(sanitize_label_value "${PEER_ID_RAW}")"

if [ "${GRAFANA_ENABLED}" = "true" ]; then
  # Pro monitoring relies on local Mimir as Grafana datasource.
  LOCAL_ENABLED="true"
fi

if [ -z "${GENERATED_CONFIG_PATH}" ]; then
  GENERATED_CONFIG_PATH="/home/ubuntu/nunet/appliance/alloy/config.generated.alloy"
fi
if [ -z "${GATEWAY_URL}" ]; then
  GATEWAY_URL="https://telemetry.orgs.nunet.network"
fi

if [ "${ENABLED}" != "true" ]; then
  echo "Plugin disabled in config; stopping Alloy."
  if [ -f "${COMPOSE_FILE}" ]; then
    docker compose -f "${COMPOSE_FILE}" -p "${COMPOSE_PROJECT}" stop mimir dcgm-exporter cadvisor grafana >> "${LOG_DIR}/apply.log" 2>&1 || true
  else
    docker stop mimir-appliance dcgm-exporter-appliance cadvisor-appliance grafana-appliance >> "${LOG_DIR}/apply.log" 2>&1 || true
  fi
  systemctl stop alloy >> "${LOG_DIR}/apply.log" 2>&1 || true
  date -u +"%Y-%m-%dT%H:%M:%SZ" > "${STATE_DIR}/stopped-at.txt"
  echo "stopped"
  exit 0
fi

if [ "${REMOTE_ENABLED}" != "true" ] && [ "${LOCAL_ENABLED}" != "true" ]; then
  echo "Both remote_enabled and local_enabled are false; stopping Alloy."
  systemctl stop alloy >> "${LOG_DIR}/apply.log" 2>&1 || true
  if [ -f "${COMPOSE_FILE}" ]; then
    docker compose -f "${COMPOSE_FILE}" -p "${COMPOSE_PROJECT}" stop mimir dcgm-exporter cadvisor grafana >> "${LOG_DIR}/apply.log" 2>&1 || true
  else
    docker stop mimir-appliance dcgm-exporter-appliance cadvisor-appliance grafana-appliance >> "${LOG_DIR}/apply.log" 2>&1 || true
  fi
  date -u +"%Y-%m-%dT%H:%M:%SZ" > "${STATE_DIR}/stopped-at.txt"
  echo "stopped"
  exit 0
fi

mkdir -p "$(dirname "${GENERATED_CONFIG_PATH}")"
TOKEN_SAFE="$(printf '%s' "${TOKEN}" | tr -d '\n\r"' | head -c 512)"
PUSH_HEADERS_LINE=""
if [ -n "${TOKEN_SAFE}" ]; then
  PUSH_HEADERS_LINE='headers = { "X-Telemetry-Token" = "'"${TOKEN_SAFE}"'" }'
fi
NODE_FORWARD_TO=""
if [ "${REMOTE_ENABLED}" = "true" ]; then
  NODE_FORWARD_TO="prometheus.remote_write.mimir.receiver"
fi
if [ "${LOCAL_ENABLED}" = "true" ]; then
  if [ -n "${NODE_FORWARD_TO}" ]; then
    NODE_FORWARD_TO="${NODE_FORWARD_TO}, "
  fi
  NODE_FORWARD_TO="${NODE_FORWARD_TO}prometheus.remote_write.local.receiver"
fi

RELABEL_RULES=""
if [ -n "${DID_LABEL}" ]; then
  RELABEL_RULES="${RELABEL_RULES}
  rule {
    action       = \"replace\"
    replacement  = $(alloy_quote "${DID_LABEL}")
    target_label = \"did\"
  }"
fi
if [ -n "${PEER_ID_LABEL}" ]; then
  RELABEL_RULES="${RELABEL_RULES}
  rule {
    action       = \"replace\"
    replacement  = $(alloy_quote "${PEER_ID_LABEL}")
    target_label = \"peer_id\"
  }"
fi

NVIDIA_SCRAPE_BLOCK=""
if [ "${DCGM_ENABLED}" = "true" ] && has_nvidia_gpu; then
  NVIDIA_SCRAPE_BLOCK='
prometheus.scrape "dcgm" {
  targets    = [{ __address__ = "127.0.0.1:9400" }]
  forward_to = [prometheus.relabel.telemetry.receiver]
}
'
fi

CADVISOR_SCRAPE_BLOCK=""
if [ "${GRAFANA_ENABLED}" = "true" ]; then
  CADVISOR_SCRAPE_BLOCK='
prometheus.scrape "cadvisor" {
  targets    = [{ __address__ = "127.0.0.1:8082" }]
  scrape_interval = "15s"
  forward_to = [prometheus.relabel.telemetry.receiver]
}
'
fi

LOKI_FORWARD_TO=""
if [ "${REMOTE_ENABLED}" = "true" ]; then
  LOKI_FORWARD_TO="loki.write.loki.receiver"
fi
LOKI_EXTRA_LABELS=""
if [ -n "${DID_LABEL}" ]; then
  LOKI_EXTRA_LABELS="${LOKI_EXTRA_LABELS}, did = $(alloy_quote "${DID_LABEL}")"
fi
if [ -n "${PEER_ID_LABEL}" ]; then
  LOKI_EXTRA_LABELS="${LOKI_EXTRA_LABELS}, peer_id = $(alloy_quote "${PEER_ID_LABEL}")"
fi

cat > "${GENERATED_CONFIG_PATH}" <<EOF
prometheus.exporter.unix "node" {}

prometheus.scrape "node" {
  targets    = prometheus.exporter.unix.node.targets
  forward_to = [prometheus.relabel.telemetry.receiver]
}
${NVIDIA_SCRAPE_BLOCK}
${CADVISOR_SCRAPE_BLOCK}
prometheus.relabel "telemetry" {
  forward_to = [${NODE_FORWARD_TO}]${RELABEL_RULES}
}
EOF
if [ "${REMOTE_ENABLED}" = "true" ]; then
  cat >> "${GENERATED_CONFIG_PATH}" <<EOF
prometheus.remote_write "mimir" {
  endpoint {
    url = "${GATEWAY_URL%/}/api/v1/push"
    ${PUSH_HEADERS_LINE}
  }
}
EOF
fi

if [ "${LOCAL_ENABLED}" = "true" ]; then
  cat >> "${GENERATED_CONFIG_PATH}" <<'EOF'
prometheus.remote_write "local" {
  endpoint {
    url = "http://127.0.0.1:9009/api/v1/push"
    headers = { "X-Scope-OrgID" = "anonymous" }
  }
}
EOF
fi

cat >> "${GENERATED_CONFIG_PATH}" <<EOF
loki.source.journal "read_alloy_service" {
  matches    = "_SYSTEMD_UNIT=alloy.service"
  forward_to = [${LOKI_FORWARD_TO}]
  labels     = { job = "journald", instance = "appliance", unit = "alloy.service"${LOKI_EXTRA_LABELS} }
}

loki.source.journal "read_sshd_service" {
  matches    = "_SYSTEMD_UNIT=sshd.service"
  forward_to = [${LOKI_FORWARD_TO}]
  labels     = { job = "journald", instance = "appliance", unit = "sshd.service"${LOKI_EXTRA_LABELS} }
}

loki.source.journal "read_docker_service" {
  matches    = "_SYSTEMD_UNIT=docker.service"
  forward_to = [${LOKI_FORWARD_TO}]
  labels     = { job = "journald", instance = "appliance", unit = "docker.service"${LOKI_EXTRA_LABELS} }
}

loki.source.journal "read_nunetdms_service" {
  matches    = "_SYSTEMD_UNIT=nunetdms.service"
  forward_to = [${LOKI_FORWARD_TO}]
  labels     = { job = "journald", instance = "appliance", unit = "nunetdms.service"${LOKI_EXTRA_LABELS} }
}

loki.source.journal "read_nunet_appliance_web_service" {
  matches    = "_SYSTEMD_UNIT=nunet-appliance-web.service"
  forward_to = [${LOKI_FORWARD_TO}]
  labels     = { job = "journald", instance = "appliance", unit = "nunet-appliance-web.service"${LOKI_EXTRA_LABELS} }
}
EOF

if [ "${REMOTE_ENABLED}" = "true" ]; then
  cat >> "${GENERATED_CONFIG_PATH}" <<EOF
loki.write "loki" {
  endpoint {
    url = "${GATEWAY_URL%/}/loki/api/v1/push"
    ${PUSH_HEADERS_LINE}
  }
}
EOF
fi

{
  if [ "${LOCAL_ENABLED}" = "true" ]; then
    ensure_mimir_config
    if [ -f "${COMPOSE_FILE}" ]; then
      docker compose -f "${COMPOSE_FILE}" -p "${COMPOSE_PROJECT}" up -d mimir
    else
      docker run -d --name mimir-appliance --restart unless-stopped \
        -p 127.0.0.1:9009:9009 \
        -v /var/lib/nunet-appliance/mimir/data:/data \
        -v /var/lib/nunet-appliance/mimir/mimir.yaml:/etc/mimir/mimir.yaml:ro \
        grafana/mimir:2.14.3 \
        -config.file=/etc/mimir/mimir.yaml
    fi
  else
    if [ -f "${COMPOSE_FILE}" ]; then
      docker compose -f "${COMPOSE_FILE}" -p "${COMPOSE_PROJECT}" stop mimir || true
    else
      docker stop mimir-appliance 2>/dev/null || true
    fi
  fi

  if [ "${DCGM_ENABLED}" = "true" ] && has_nvidia_gpu; then
    if [ -f "${COMPOSE_FILE}" ]; then
      docker compose -f "${COMPOSE_FILE}" -p "${COMPOSE_PROJECT}" up -d dcgm-exporter
    fi
  else
    if [ -f "${COMPOSE_FILE}" ]; then
      docker compose -f "${COMPOSE_FILE}" -p "${COMPOSE_PROJECT}" stop dcgm-exporter || true
    else
      docker stop dcgm-exporter-appliance 2>/dev/null || true
    fi
  fi

  if [ "${GRAFANA_ENABLED}" = "true" ]; then
    if [ -f "${COMPOSE_FILE}" ]; then
      ensure_grafana_dashboards
      docker compose -f "${COMPOSE_FILE}" -p "${COMPOSE_PROJECT}" up -d cadvisor grafana
    fi
  else
    if [ -f "${COMPOSE_FILE}" ]; then
      docker compose -f "${COMPOSE_FILE}" -p "${COMPOSE_PROJECT}" stop cadvisor grafana || true
    else
      docker stop cadvisor-appliance grafana-appliance 2>/dev/null || true
    fi
  fi

  mkdir -p /var/lib/nunet-appliance/alloy
  ensure_alloy_service_override
  cp -f "${GENERATED_CONFIG_PATH}" /var/lib/nunet-appliance/alloy/config.alloy
  chown alloy:alloy /var/lib/nunet-appliance/alloy/config.alloy 2>/dev/null || true
  chmod 640 /var/lib/nunet-appliance/alloy/config.alloy
  systemctl enable alloy.service 2>/dev/null || true
  systemctl restart alloy
} >> "${LOG_DIR}/apply.log" 2>&1

date -u +"%Y-%m-%dT%H:%M:%SZ" > "${STATE_DIR}/applied-at.txt"
echo "applied"
