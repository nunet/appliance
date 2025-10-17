# Backend Modules Guide

> The goal of this directory is to expose a **thin, well‑documented helper layer** for the FastAPI application that lives in `backend/nunet_api`.  
> Anything that is not required by the API surface should stay out of `backend/modules`.

---

## 1. Inventory & Responsibilities

The table below shows every module that currently lives here, what it does, and which FastAPI routers consume it. Use this as the single source of truth when deciding whether a helper can be modified or removed.

| Module | High-level responsibility | Primary public API | Routers consuming it |
| --- | --- | --- | --- |
| **`caddy_proxy_manager.py`** | Manage installation and lifecycle of the Caddy proxy service that fronts onboarding HTTPS traffic. | `install_systemd_service()`, `get_caddy_proxy_status()` | `organizations.py` |
| **`ddns_manager.py`** | Register/update DDNS entries for deployments, verify propagation, inspect DDNS-enabled containers. | `register_ddns()`, `list_ddns_containers()`, `force_ddns_update()` | `ensemble.py` (manifest enrichment) |
| **`docker_manager.py`** | Lightweight wrapper around `docker` CLI to check service health and enumerates running containers. | `check_docker_status()`, `get_running_containers()` | Used by `ddns_manager.py` |
| **`dms_manager.py`** | High-level DMS operations: restart, status, onboarding scripts, resource queries, log collection. | `get_dms_version()`, `check_dms_installation()`, `restart_dms()`, `get_structured_logs()` | `dms.py`, `payments.py`, `proc.py`, `stream.py` |
| **`dms_utils.py`** | Low-level DMS execution helpers with caching and passphrase injection. | `run_dms_command_with_passphrase()`, `get_cached_dms_status_info()`, `get_cached_dms_resource_info()` | Imported by multiple routers and modules (`dms_manager`, `ensemble`, `payments`, `organizations`) |
| **`ensemble_manager_v2.py`** | API-friendly deployment manager: list deployments, fetch manifests, read saved YAML, submit/shutdown ensembles. | `get_deployments_for_web()`, `view_running_ensembles()`, `get_deployment_status()`, `deploy_ensemble()` | `ensemble.py`, `stream.py` |
| **`ensemble_utils.py`** | Template processing and validation helpers for the deployment UI. | `process_yaml_template()`, `validate_form_data()`, `save_deployment_instance()`, `get_deployment_options()` | `ensemble.py`, `ensemble_schema.py` |
| **`onboarding_manager.py`** | Persist onboarding state, talk to the onboarding API, manage capability tokens and service restarts. | `get_onboarding_status()`, `api_submit_join()`, `api_check_status()`, `process_post_approval_payload()` | `organizations.py` |
| **`organization_manager.py`** | Thin wrapper around org joining scripts. | `join_organization()`, `get_organization_status()` | `organizations.py` |
| **`org_utils.py`** | Helper utilities to read and interpret organization capability files. | `load_known_organizations()`, `get_joined_organizations_with_names()` | `organizations.py`, `onboarding_manager.py` |
| **`utils.py`** | System information helpers: IP detection, appliance version, SSH status. | `get_local_ip()`, `get_public_ip()`, `get_appliance_version()`, `get_ssh_status()` | `sysinfo.py`, `dms.py`, `stream.py` |

> **Note:** Each module intentionally keeps only the functions that are imported by the routers. If you need additional behaviour, add it here and update this README accordingly.

---

## 2. Usage Patterns & Guidance

### 2.1 DMS interaction
* Always route DMS CLI calls through `dms_utils.run_dms_command_with_passphrase()` to ensure the passphrase and logging behaviour are consistent.
* Cache-friendly helpers (`get_cached_dms_status_info`, `get_cached_dms_resource_info`) are safe to reuse; they expose `force_refresh` for bypassing caches when required by the API.
* `dms_manager.DMSManager` is the “high-level” façade used by the routers. When adding features, prefer to implement the logic in `dms_manager` and delegate to `dms_utils` for execution/caching.

### 2.2 Ensemble management
* The rewritten `ensemble_manager_v2` is **API centric**: no TUI leftovers, no menus, no user prompts.
* It resolves manifests and deployment YAML paths defensively; if you add new methods, keep the error semantics (return dicts with `status`/`message`) so the routers can forward responses without extra wrapping.
* `ensemble_utils` owns all YAML template operations. When you add fields or validation logic, remember to also update the frontend schema expectations (`frontend/src/api/ensembles.ts`).

### 2.3 Onboarding & organizations
* Onboarding state is persisted under `~/nunet/appliance/onboarding_state.json`. `onboarding_manager` ensures the file exists before writing; if you introduce new state keys, default them in `_baseline_state`.
* `organization_manager` is a thin shim over shell scripts (`join-org-web.sh`). Avoid embedding script logic here—keep it as a subprocess runner that returns structured responses.
* `org_utils` is imported by both managers. Keep its functions pure (no subprocess calls) so they remain easy to unit-test.

### 2.4 DDNS & Docker
* `ddns_manager` now depends on the minimal `docker_manager`. If you expand Docker usage (e.g. pulling logs), add the helper inside `docker_manager` and reuse it from DDNS rather than shelling out directly.
* `ddns_manager.make_dns_label()` mirrors the legacy naming scheme; adjust the helper if the contract changes in the deployment manifest logic (`ensemble_manager_v2.enrich_manifest_payload`).

### 2.5 Utilities
* `utils.get_appliance_version()` checks, in order: `APPLIANCE_VERSION_PATH`, the system file `/home/ubuntu/nunet/appliance/appliance_version.txt`, and the repo `backend/version.txt`. If you provision a different path, set the env var so the API responds correctly.
* `get_public_ip()` rate-limits lookups with a simple JSON cache. If you introduce more frequent polling, reconsider using that helper or extend it with configurable TTL.

---

## 3. Quick Import Matrix

This matrix links each router to the modules it relies on. Use it to ensure you don’t accidentally break an endpoint while refactoring.

| Router (`backend/nunet_api/routers`) | Modules imported from `backend/modules` |
| --- | --- |
| `auth.py` | – (no module dependencies) |
| `dms.py` | `dms_manager`, `dms_utils`, `onboarding_manager`, `ddns_manager` (via manifest enrichment) |
| `sysinfo.py` | `utils` |
| `ensemble.py` | `ensemble_manager_v2`, `ensemble_utils`, `ddns_manager` (indirect) |
| `ensemble_schema.py` | `ensemble_manager_v2`, `ensemble_utils` |
| `stream.py` | `ensemble_manager_v2`, `dms_utils` |
| `organizations.py` | `onboarding_manager`, `organization_manager`, `org_utils`, `dms_utils`, `caddy_proxy_manager`, `dms_manager` |
| `payments.py` | `dms_manager`, `dms_utils` |
| `proc.py` | `dms_manager`, `dms_utils` |

---

## 4. Frequently Asked Questions

**Q: I need a helper that runs a shell command. Where should it go?**  
A: If it is DMS-related, put it in `dms_manager` or `dms_utils`. For general shell utilities, consider whether it belongs in a new module or inside an existing manager. Keep the command names in a constant and wrap them in a function that returns structured output.

**Q: Can I share code between managers?**  
A: Yes, but prefer small, pure helper functions (e.g. in `utils` or a new shared module) instead of cross-importing managers, to avoid circular dependencies.

---
