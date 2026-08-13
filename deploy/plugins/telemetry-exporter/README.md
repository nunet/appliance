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
- `dcgm_exporter_enabled` (bool): enable NVIDIA DCGM exporter scrape when a GPU is present
- `grafana_enabled` (bool): enable local Grafana + cAdvisor
- `dms_metrics_enabled` (bool, default true): run the independent DMS metrics exporter and scrape it
- `dms_metrics_listen` (string, default `127.0.0.1:9105`): exporter bind address
- `dms_metrics_scrape_interval` (string, default `60s`): Alloy scrape interval for DMS metrics
- `gateway_url` (string): remote destination base URL
- `telemetry_token` (string): token for `X-Telemetry-Token`; empty means not configured
- `generated_config_path` (string): path to generated Alloy config

## DMS metrics exporter

`dms-metrics/server.py` is a stdlib-only always-on Prometheus exporter. It queries DMS actor
endpoints (`resources/*`, onboarding, hardware, peers, deployments) and serves `/metrics` for
Alloy to scrape into remote and/or local Mimir via the existing remote_write pipeline.

Lifecycle:

- `install.sh` installs `nunet-dms-metrics.service`
- `apply.sh` starts/stops it based on `dms_metrics_enabled` and adds an Alloy scrape target
- `remove.sh` stops and removes the unit

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
