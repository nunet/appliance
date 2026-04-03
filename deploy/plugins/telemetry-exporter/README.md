# Telemetry Exporter Plugin

This plugin defines a first-class lifecycle for the Alloy-based telemetry exporter.
It is intended to be run by a root plugin runner (for example from `nunet-appliance-updater.service`).

## Files

- `manifest.json`: plugin identity, paths, capabilities, and hook entrypoints
- `default-config.json`: initial desired-state config (no default telemetry token)
- `hooks/install.sh`: install/upgrade Alloy and service drop-in
- `hooks/apply.sh`: apply generated Alloy config or stop Alloy if disabled
- `hooks/status.sh`: output plugin and runtime status as JSON
- `hooks/remove.sh`: disable plugin resources (optional package purge)

## Config Contract

Config path (default):

`/home/ubuntu/nunet/appliance/plugins/telemetry-exporter/config.json`

Supported keys:

- `enabled` (bool): desired plugin state
- `remote_enabled` (bool): desired remote push state
- `local_enabled` (bool): desired local collection state
- `gateway_url` (string): remote destination base URL
- `telemetry_token` (string): token for `X-Telemetry-Token`; empty means not configured
- `generated_config_path` (string): path to generated Alloy config

## Lifecycle Sequence

Typical execution order by plugin runner:

1. `install.sh <config-path>`
2. `apply.sh <config-path>`
3. `status.sh <config-path>` (for reporting)
4. `remove.sh` (when plugin is disabled/uninstalled)

## Notes

- The plugin intentionally has **no default token**.
- `install.sh` uses `--skip-config` so install does not overwrite generated config.
- `apply.sh` expects `generated_config_path` to already exist (from backend config generation step).
