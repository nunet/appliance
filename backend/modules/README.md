# Backend Modules Guide

> This directory hosts the thin, well-documented helper layer that backs the FastAPI app in `backend/nunet_api`. Anything that is not required by the API surface should stay out of `backend/modules`.

---

## 1. Inventory & Responsibilities

The table below lists the modules in this package, what they do, and which routers call into them. Treat it as the source of truth before adding or removing helpers.

| Module | High-level responsibility | Primary public API | Routers consuming it |
| --- | --- | --- | --- |
| `caddy_proxy_manager.py` | Manage installation and lifecycle of the Caddy proxy that fronts onboarding HTTPS traffic. | `install_systemd_service()`, `get_caddy_proxy_status()` | `organizations.py` |
| `ddns_manager.py` | Register/update DDNS entries for deployments, verify propagation, inspect DDNS-enabled containers. | `register_ddns()`, `list_ddns_containers()`, `force_ddns_update()` | `ensemble.py` (manifest enrichment) |
| `docker_manager.py` | Lightweight wrapper around the `docker` CLI to check service health and enumerate running containers. | `check_docker_status()`, `get_running_containers()` | Used by `ddns_manager.py` |
| `dms_manager.py` | High-level DMS orchestration: service lifecycle, status, onboarding scripts, contract flows, resource queries, log collection. | `get_dms_version()`, `check_dms_installation()`, `list_incoming_contracts()`, `create_contract()`, `approve_contract()`, `get_structured_logs()` | `dms.py`, `payments.py`, `contracts.py`, `proc.py`, `stream.py` |
| `dms_utils.py` | Low-level DMS execution helpers with caching, passphrase injection, and shared command result envelopes. | `run_dms_command_with_passphrase()`, `get_cached_dms_status_info()`, `contract_list_incoming()`, `contract_state()`, `contract_create()`, `contract_approve_local()` | Imported by `dms_manager`, `contracts`, `ensemble`, `payments`, `organizations` |
| `ensemble_manager_v2.py` | API-friendly deployment manager: list deployments, fetch manifests, read saved YAML, submit/shutdown ensembles. | `get_deployments_for_web()`, `view_running_ensembles()`, `get_deployment_status()`, `deploy_ensemble()` | `ensemble.py`, `stream.py` |
| `ensemble_utils.py` | Template processing and validation helpers for the deployment UI. | `process_yaml_template()`, `validate_form_data()`, `save_deployment_instance()`, `get_deployment_options()` | `ensemble.py`, `ensemble_schema.py` |
| `onboarding_manager.py` | Persist onboarding state, talk to the upstream onboarding API, manage capability tokens, restart services. | `get_onboarding_status()`, `api_submit_join()`, `api_check_status()`, `process_post_approval_payload()` | `organizations.py` |
| `organization_manager.py` | Thin wrapper around organization joining scripts. | `join_organization()`, `get_organization_status()` | `organizations.py` |
| `org_utils.py` | Parse organization capability files and related metadata. | `load_known_organizations()`, `get_joined_organizations_with_names()` | `organizations.py`, `onboarding_manager.py` |
| `upnp_manager.py` | UPnP router discovery and automatic port forwarding for appliance external accessibility. | `discover_gateway()`, `list_port_mappings()`, `add_port_mapping()`, `configure_appliance_port_forwarding()`, `get_appliance_status()` | `upnp.py` |
| `utils.py` | System information helpers: IP detection, appliance version, SSH status. | `get_local_ip()`, `get_public_ip()`, `get_appliance_version()`, `get_ssh_status()` | `sysinfo.py`, `dms.py`, `stream.py` |

---

## 2. Usage Patterns & Guidance

### 2.1 DMS interaction
* Always call DMS CLI commands via `dms_utils.run_dms_command_with_passphrase()` so the passphrase and logging behaviour stay consistent.
* Reuse the cache-friendly helpers (`get_cached_dms_status_info`, `get_cached_dms_resource_info`) and reach for `force_refresh=True` when an endpoint needs a fresh view.
* Contract commands use the shared `DmsCommandResult` shape. Wrap new verbs with helpers similar to `contract_list_incoming`, `contract_state`, `contract_create`, or `contract_approve_local` so stdout/stderr, argv, and parsed JSON are preserved for logging.
* `dms_manager.DMSManager` is the high-level facade that routers depend on. Keep orchestration logic here and delegate subprocess execution to `dms_utils`. Use `_contract_success` / `_contract_error` when adding contract operations to maintain consistent API responses.

### 2.2 Ensemble management
* `ensemble_manager_v2` is API-centric (no TUI remnants, menus, or prompts). Return dicts with `status`/`message` so routers can forward responses directly.
* `ensemble_utils` owns YAML/template manipulation. When adding fields or validation rules, update the frontend schema helpers (`frontend/src/api/ensembles.ts`) accordingly.

### 2.3 Onboarding & organizations
* Onboarding state persists under `~/nunet/appliance/onboarding_state.json`. Default any new keys in `_baseline_state`.
* `organization_manager` remains a subprocess shim over scripts such as `join-org-web.sh`. Avoid embedding script logic directly in Python.
* `org_utils` is shared by both managers. Keep functions pure (no subprocess calls) to retain easy unit testing.

### 2.4 DDNS & Docker
* `ddns_manager` depends on `docker_manager`. Add new Docker functionality there and import it instead of shelling out from multiple places.
* `ddns_manager.make_dns_label()` mirrors the legacy naming scheme; adjust it if the manifest contract changes inside `ensemble_manager_v2.enrich_manifest_payload`.

### 2.5 Utilities
* `utils.get_appliance_version()` checks, in order: `APPLIANCE_VERSION_PATH`, `/home/ubuntu/nunet/appliance/appliance_version.txt`, and `backend/version.txt`. Override the env var if you store the version elsewhere.
* `utils.get_public_ip()` caches lookups with a simple TTL. Extend or bypass the cache if you need higher-frequency polling.

---

## 3. Quick Import Matrix

This matrix links each router to the modules it imports from `backend/modules`.

| Router (`backend/nunet_api/routers`) | Modules imported from `backend/modules` |
| --- | --- |
| `auth.py` | *(no module dependencies)* |
| `dms.py` | `dms_manager`, `dms_utils`, `onboarding_manager`, `ddns_manager` (via manifest enrichment) |
| `sysinfo.py` | `utils` |
| `ensemble.py` | `ensemble_manager_v2`, `ensemble_utils`, `ddns_manager` (indirect) |
| `ensemble_schema.py` | `ensemble_manager_v2`, `ensemble_utils` |
| `stream.py` | `ensemble_manager_v2`, `dms_utils` |
| `organizations.py` | `onboarding_manager`, `organization_manager`, `org_utils`, `dms_utils`, `caddy_proxy_manager`, `dms_manager` |
| `payments.py` | `dms_manager`, `dms_utils` |
| `contracts.py` | `dms_manager`, `dms_utils` |
| `proc.py` | `dms_manager`, `dms_utils` |
| `upnp.py` | `upnp_manager` |

---

## 4. Frequently Asked Questions

**Q: I need a helper that runs a shell command. Where should it go?**
> If it is DMS-related, put it in `dms_manager` or `dms_utils`. For general utilities, consider a new module or an existing manager. Keep command invocations isolated and return structured data.

**Q: Can I share code between managers?**
> Yes, but favour small, pure helper functions (for example in `utils`) over cross-importing managers to avoid circular dependencies.

---
