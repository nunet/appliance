#!/usr/bin/env bash
set -euo pipefail

# Root plugin manager for appliance plugins.
# Primary command:
#   plugin-manager.sh sync
#
# Design goals:
# - Idempotent lifecycle execution (install/apply only when needed)
# - Serialized execution (single lock, avoids apt/dpkg contention)
# - Generic plugin manifests with hook paths
# - Telemetry effective-config merge from contrib fragments

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_ROOT_DEFAULT="/home/ubuntu/nunet/appliance"
APP_ROOT="${APP_ROOT:-$APP_ROOT_DEFAULT}"

if [[ "${SCRIPT_DIR}" == /usr/lib/nunet-appliance-web* ]] && [ -d "/usr/lib/nunet-appliance-web/plugins" ]; then
  PLUGINS_DIR="/usr/lib/nunet-appliance-web/plugins"
else
  # Dev mode: run from repo checkout where this script lives.
  PLUGINS_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)/plugins"
fi

STATE_ROOT="/var/lib/nunet-appliance/plugins"
LOG_ROOT="/var/log/nunet-appliance/plugins"
LOCK_FILE="/var/lib/nunet-appliance/plugin-manager.lock"
CONFIG_OWNER_USER="${CONFIG_OWNER_USER:-ubuntu}"
CONFIG_OWNER_GROUP="${CONFIG_OWNER_GROUP:-ubuntu}"

mkdir -p "${STATE_ROOT}" "${LOG_ROOT}" "$(dirname "${LOCK_FILE}")"

log() { echo "[plugin-manager] $*"; }

usage() {
  cat <<'EOF'
Usage:
  plugin-manager.sh sync [plugin-id]
  plugin-manager.sh status
  plugin-manager.sh run <plugin-id> <install|apply|status|remove>

Environment:
  APP_ROOT=/home/ubuntu/nunet/appliance
EOF
}

json_read() {
  local file="$1"
  local key="$2"
  python3 - "$file" "$key" <<'PY'
import json, sys
path, key = sys.argv[1], sys.argv[2]
parts = [p for p in key.split(".") if p]
with open(path, "r", encoding="utf-8") as f:
    data = json.load(f)
cur = data
for p in parts:
    if isinstance(cur, dict):
        cur = cur.get(p)
    else:
        cur = None
        break
if isinstance(cur, bool):
    print("true" if cur else "false")
elif cur is None:
    print("")
else:
    print(str(cur))
PY
}

ensure_config_exists() {
  local manifest="$1"
  local plugin_dir="$2"
  local config_path default_rel default_abs
  config_path="$(json_read "$manifest" "config.path")"
  default_rel="$(json_read "$manifest" "config.default_path")"
  default_abs="${plugin_dir}/${default_rel}"
  [ -n "$config_path" ] || return 0
  if [ ! -f "$config_path" ]; then
    mkdir -p "$(dirname "$config_path")"
    if [ -f "$default_abs" ]; then
      cp "$default_abs" "$config_path"
    else
      printf '{}\n' > "$config_path"
    fi
  fi
  # Desired-state config should remain writable by the web service user.
  chown -R "${CONFIG_OWNER_USER}:${CONFIG_OWNER_GROUP}" "$(dirname "$config_path")" 2>/dev/null || true
  chmod 0755 "$(dirname "$config_path")" 2>/dev/null || true
  chown "${CONFIG_OWNER_USER}:${CONFIG_OWNER_GROUP}" "$config_path" 2>/dev/null || true
  chmod 0644 "$config_path" 2>/dev/null || true
}

build_effective_config() {
  local plugin_id="$1"
  local config_path="$2"
  local state_dir="$3"
  local effective_path="${state_dir}/effective-config.json"

  # Generic behavior: effective == desired config.
  if [ "$plugin_id" != "telemetry-exporter" ]; then
    cp "$config_path" "$effective_path"
    echo "$effective_path"
    return 0
  fi

  # Telemetry-specific merge:
  # base config + all contrib fragments under:
  #   /home/ubuntu/nunet/appliance/plugins/telemetry-exporter/contrib.d/*.json
  # Later files override earlier values (sorted lexicographically).
  local contrib_dir="${APP_ROOT}/plugins/telemetry-exporter/contrib.d"
  python3 - "$config_path" "$contrib_dir" "$effective_path" <<'PY'
import json, pathlib, sys
base_path = pathlib.Path(sys.argv[1])
contrib_dir = pathlib.Path(sys.argv[2])
out_path = pathlib.Path(sys.argv[3])

def deep_merge(dst, src):
    for k, v in src.items():
        if isinstance(v, dict) and isinstance(dst.get(k), dict):
            deep_merge(dst[k], v)
        else:
            dst[k] = v
    return dst

with base_path.open("r", encoding="utf-8") as f:
    merged = json.load(f)

contributors = []
if contrib_dir.is_dir():
    for p in sorted(contrib_dir.glob("*.json")):
        try:
            with p.open("r", encoding="utf-8") as f:
                fragment = json.load(f)
            deep_merge(merged, fragment)
            contributors.append(p.name)
        except Exception as e:
            # Keep merge resilient: skip malformed fragments.
            contributors.append(f"{p.name}:error:{e.__class__.__name__}")

meta = merged.get("_meta", {})
meta["contributors"] = contributors
merged["_meta"] = meta

out_path.parent.mkdir(parents=True, exist_ok=True)
with out_path.open("w", encoding="utf-8") as f:
    json.dump(merged, f, indent=2, sort_keys=True)
PY
  echo "$effective_path"
}

sha256_file() {
  local path="$1"
  python3 - "$path" <<'PY'
import hashlib, pathlib, sys
p = pathlib.Path(sys.argv[1])
h = hashlib.sha256(p.read_bytes()).hexdigest()
print(h)
PY
}

load_state_value() {
  local state_json="$1"
  local key="$2"
  [ -f "$state_json" ] || { echo ""; return 0; }
  json_read "$state_json" "$key"
}

save_state() {
  local state_json="$1"
  local version="$2"
  local hash="$3"
  local status="$4"
  python3 - "$state_json" "$version" "$hash" "$status" <<'PY'
import json, pathlib, sys, datetime
path = pathlib.Path(sys.argv[1])
version = sys.argv[2]
cfg_hash = sys.argv[3]
status = sys.argv[4]
data = {}
if path.is_file():
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        data = {}
data["installed_version"] = version
data["last_applied_config_sha256"] = cfg_hash
data["last_status"] = status
data["updated_at"] = datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
PY
}

run_hook() {
  local hook_path="$1"
  local config_path="$2"
  local log_file="$3"
  shift 3
  if [ ! -x "$hook_path" ]; then
    echo "Hook not executable: $hook_path" >&2
    return 1
  fi
  "$hook_path" "$config_path" "$@" >> "$log_file" 2>&1
}

sync_one_plugin() {
  local plugin_dir="$1"
  local manifest="${plugin_dir}/manifest.json"
  [ -f "$manifest" ] || return 0

  local plugin_id plugin_version config_path lifecycle_install lifecycle_apply lifecycle_status
  plugin_id="$(json_read "$manifest" "id")"
  plugin_version="$(json_read "$manifest" "version")"
  config_path="$(json_read "$manifest" "config.path")"
  lifecycle_install="$(json_read "$manifest" "lifecycle.install")"
  lifecycle_apply="$(json_read "$manifest" "lifecycle.apply")"
  lifecycle_status="$(json_read "$manifest" "lifecycle.status")"

  [ -n "$plugin_id" ] || { log "Skipping plugin with missing id: $manifest"; return 0; }
  [ -n "$config_path" ] || { log "Skipping $plugin_id (missing config.path)"; return 0; }

  ensure_config_exists "$manifest" "$plugin_dir"

  local state_dir log_dir state_json
  state_dir="${STATE_ROOT}/${plugin_id}"
  log_dir="${LOG_ROOT}/${plugin_id}"
  state_json="${state_dir}/state.json"
  mkdir -p "$state_dir" "$log_dir"

  local effective_config config_hash installed_version previous_hash enabled
  effective_config="$(build_effective_config "$plugin_id" "$config_path" "$state_dir")"
  config_hash="$(sha256_file "$effective_config")"
  installed_version="$(load_state_value "$state_json" "installed_version")"
  previous_hash="$(load_state_value "$state_json" "last_applied_config_sha256")"
  enabled="$(json_read "$effective_config" "enabled")"
  [ -n "$enabled" ] || enabled="false"

  local install_hook_path apply_hook_path status_hook_path
  install_hook_path="${plugin_dir}/${lifecycle_install}"
  apply_hook_path="${plugin_dir}/${lifecycle_apply}"
  status_hook_path="${plugin_dir}/${lifecycle_status}"

  local install_ran="false"
  if [ "$installed_version" != "$plugin_version" ]; then
    log "Installing/upgrading plugin ${plugin_id} (${installed_version:-none} -> ${plugin_version})"
    run_hook "$install_hook_path" "$effective_config" "${log_dir}/install.log"
    install_ran="true"
  fi

  # Apply whenever config changed, plugin upgraded, or plugin is explicitly disabled.
  if [ "$install_ran" = "true" ] || [ "$config_hash" != "$previous_hash" ] || [ "$enabled" = "false" ]; then
    log "Applying plugin ${plugin_id} (enabled=${enabled})"
    if [ "$plugin_id" = "telemetry-exporter" ]; then
      local telemetry_did telemetry_peer_id
      telemetry_did="$(json_read "$effective_config" "did")"
      telemetry_peer_id="$(json_read "$effective_config" "peer_id")"
      run_hook "$apply_hook_path" "$effective_config" "${log_dir}/apply.log" "$telemetry_did" "$telemetry_peer_id"
    else
      run_hook "$apply_hook_path" "$effective_config" "${log_dir}/apply.log"
    fi
  fi

  local status_value="unknown"
  if [ -x "$status_hook_path" ]; then
    status_value="$("$status_hook_path" "$effective_config" 2>/dev/null || echo "unknown")"
    echo "$status_value" > "${state_dir}/last-status.json"
  fi

  save_state "$state_json" "$plugin_version" "$config_hash" "$status_value"
  log "Plugin ${plugin_id} synced."
}

list_plugins() {
  local p
  for p in "${PLUGINS_DIR}"/*; do
    [ -d "$p" ] || continue
    [ -f "$p/manifest.json" ] || continue
    echo "$p"
  done
}

cmd_sync() {
  local only_plugin="${1:-}"
  if [ ! -d "$PLUGINS_DIR" ]; then
    log "Plugins directory not found: ${PLUGINS_DIR}"
    return 0
  fi
  if [ -n "$only_plugin" ]; then
    local target="${PLUGINS_DIR}/${only_plugin}"
    if [ ! -d "$target" ]; then
      echo "Plugin not found: ${only_plugin}" >&2
      return 1
    fi
    sync_one_plugin "$target"
    return 0
  fi
  local plugin_dir
  while IFS= read -r plugin_dir; do
    sync_one_plugin "$plugin_dir"
  done < <(list_plugins)
}

cmd_status() {
  if [ ! -d "$STATE_ROOT" ]; then
    echo "{}"
    return 0
  fi
  python3 - "$STATE_ROOT" <<'PY'
import json, pathlib, sys
root = pathlib.Path(sys.argv[1])
out = {}
for p in sorted(root.glob("*/state.json")):
    plugin = p.parent.name
    try:
        out[plugin] = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        out[plugin] = {"error": "invalid state"}
print(json.dumps(out, indent=2, sort_keys=True))
PY
}

cmd_run() {
  local plugin_id="${1:-}"
  local action="${2:-}"
  [ -n "$plugin_id" ] || { usage; return 2; }
  [ -n "$action" ] || { usage; return 2; }
  local plugin_dir="${PLUGINS_DIR}/${plugin_id}"
  local manifest="${plugin_dir}/manifest.json"
  [ -f "$manifest" ] || { echo "Plugin not found: ${plugin_id}" >&2; return 1; }
  ensure_config_exists "$manifest" "$plugin_dir"
  local config_path hook_rel hook_abs
  config_path="$(json_read "$manifest" "config.path")"
  hook_rel="$(json_read "$manifest" "lifecycle.${action}")"
  [ -n "$hook_rel" ] || { echo "Lifecycle '${action}' not defined for ${plugin_id}" >&2; return 1; }
  hook_abs="${plugin_dir}/${hook_rel}"
  if [ "$plugin_id" = "telemetry-exporter" ] && [ "$action" = "apply" ]; then
    local telemetry_did telemetry_peer_id
    telemetry_did="$(json_read "$config_path" "did")"
    telemetry_peer_id="$(json_read "$config_path" "peer_id")"
    run_hook "$hook_abs" "$config_path" "${LOG_ROOT}/${plugin_id}/${action}.log" "$telemetry_did" "$telemetry_peer_id"
  else
    run_hook "$hook_abs" "$config_path" "${LOG_ROOT}/${plugin_id}/${action}.log"
  fi
}

main() {
  local cmd="${1:-sync}"
  shift || true

  exec 9>"${LOCK_FILE}"
  if ! flock -n 9; then
    echo "plugin-manager already running; exiting." >&2
    return 0
  fi

  case "$cmd" in
    sync) cmd_sync "${1:-}" ;;
    status) cmd_status ;;
    run) cmd_run "${1:-}" "${2:-}" ;;
    -h|--help|help) usage ;;
    *)
      usage
      return 2
      ;;
  esac
}

main "$@"
