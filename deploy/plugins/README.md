# Plugin Manager Contract

`plugin-manager.sh` is the root lifecycle executor for appliance plugins.

## Runtime paths

- Plugin manager: `/usr/lib/nunet-appliance-web/plugin-manager.sh`
- Installed plugins: `/usr/lib/nunet-appliance-web/plugins/<plugin-id>/`
- Desired plugin config: `/home/ubuntu/nunet/appliance/plugins/<plugin-id>/config.json`
- Plugin state: `/var/lib/nunet-appliance/plugins/<plugin-id>/state.json`
- Plugin logs: `/var/log/nunet-appliance/plugins/<plugin-id>/`

## Lifecycle model

Manifest fields used by the manager:

- `id`
- `version`
- `config.path`
- `config.default_path`
- `lifecycle.install`
- `lifecycle.apply`
- `lifecycle.status`
- `lifecycle.remove` (used by `plugin-manager.sh run <id> remove`)

Sync behavior:

1. Ensure config file exists (copy default if missing).
2. Build effective config.
3. Run `install` only when `state.installed_version != manifest.version`.
4. Run `apply` when effective config hash changes or install ran.
5. Run `status`, then persist state.

## Telemetry contribution model

Telemetry supports contribution fragments from other plugins:

- Base config: `/home/ubuntu/nunet/appliance/plugins/telemetry-exporter/config.json`
- Contrib dir: `/home/ubuntu/nunet/appliance/plugins/telemetry-exporter/contrib.d/`
- Fragment files: `*.json` (merged in lexicographic filename order)

Effective config is written to:

- `/var/lib/nunet-appliance/plugins/telemetry-exporter/effective-config.json`

### Suggested contributor keys

Use only plugin-owned keys and avoid editing another plugin's base config directly.

- `scrape_targets`: list of extra metrics scrape targets (for example cadvisor)
- `journal_units`: list of units to include in log collection
- `remote_writes`: optional additional remote write endpoints
- `requires`: plugin dependency hints (for observability graph)

The telemetry plugin should own schema validation and config generation for these keys.
Other plugins should contribute fragments only and let telemetry decide final wiring.
