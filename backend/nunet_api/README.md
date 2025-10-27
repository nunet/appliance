# NuNet FastAPI Application Guide

This document describes the current FastAPI application that powers the appliance API.  
The app lives in `backend/nunet_api` and is designed to be stateless, authenticated, and focused on supporting the new frontend.

---

## 1. Application Entry Point

* **`main.py`** constructs the FastAPI app, applies middleware, mounts the SPA (the built frontend), and wires routers.
  * Middleware applied:
    * `GZipMiddleware` (≥1KB responses compressed)
    * `CORSMiddleware` (allows all origins; tighten when deploying if needed)
  * Static files: the SPA is served either from `$NUNET_STATIC_DIR` or `../frontend/dist`
  * Health endpoint: `GET /health`
* **Authentication** is enforced on every router except `/auth`, `/health`, `/setup`, and `/login`.
  * Requirement enforcement is handled via the `protected = [Depends(require_auth)]` dependency list.
  * The storage and refresh of tokens live in `hooks/useAuth` on the frontend.

---

## 2. Routers Overview

Each router defines API endpoints grouped by functional area. The table below lists every router, its route prefix, the modules it depends on, and the key endpoints it exposes.

| Router file | Prefix | Dependencies (`modules.*`) | Notable endpoints |
| --- | --- | --- | --- |
| **`routers/auth.py`** | `/auth` | – | `POST /auth/login`, `GET /auth/status`, `POST /auth/setup` |
| **`routers/dms.py`** | `/dms` | `dms_manager`, `dms_utils`, `onboarding_manager` | DMS version/install/status/logs, compute onboarding & offboarding actions |
| **`routers/sysinfo.py`** | `/sys` | `utils` | Local IP, public IP, appliance version, SSH status, docker containers |
| **`routers/ensemble.py`** | `/ensemble` | `ensemble_manager_v2`, `ensemble_utils`, `dms_manager`, `dms_utils`, `ddns_manager` | Deployment CRUD (list, status, manifest, logs, allocations), template copying, deployment from template |
| **`routers/ensemble_schema.py`** | `/ensemble` | `ensemble_manager_v2`, `ensemble_utils` | Template upload, schema inference, template retrieval |
| **`routers/organizations.py`** | `/organizations` | `onboarding_manager`, `organization_manager`, `org_utils`, `dms_utils`, `caddy_proxy_manager`, `dms_manager` | Wizard endpoints (known orgs, join flow, status polling, processing payloads) |
| **`routers/payments.py`** | `/payments` | `dms_manager` | List DMS transactions, confirm transactions |
| **`routers/auth.py`** | `/auth` | – | Setup/login/token refresh |

> NOTE: The `/ensemble` prefix is shared by both `ensemble.py` and `ensemble_schema.py`. The former handles runtime operations, the latter focuses on template creation and upload.

---

## 3. Authentication & Security

* Authentication is bearer-token based.
  * `/auth/login` issues a token (JWT via `PyJWT`)
  * `/auth/status` checks if a password exists
  * `/auth/setup` allows initial password creation (first boot only)
* `security.py` centralizes token validation and dependency injection.
  * `require_auth` raises `HTTPException(401)` if the token is invalid or missing.
* All application endpoints are HTTP-based. Any previous WebSocket helpers have been removed.
* Some endpoints rely on local binaries or scripts (`sudo`, `docker`, `nunet`). They catch `FileNotFoundError` to provide API-friendly errors (e.g. Docker not installed).

---

## 4. External Dependencies & Installation

All Python dependencies are listed in `backend/nunet_api/requirements.txt`.  
Top-level highlights:

* **FastAPI** + **Uvicorn** – API framework and ASGI server.
* **PyJWT** – token signing and verification.
* **python-multipart** – file uploads for template management.
* **passlib/bcrypt** – password hashing for the admin user.
* **httpx** – asynchronous HTTP client used by onboarding flows.
* **Platform requirements**: `nunet` CLI, `sudo`, `docker`, `curl`, `dig`, `journalctl`, `systemctl` depending on the endpoint.

Install for development:

```bash
cd backend/nunet_api
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn nunet_api.main:app --host 127.0.0.1 --port 8081 --reload
```

---

## 5. Middleware & Static Serving

* Static SPA mount expects the built frontend under:
  * `$NUNET_STATIC_DIR`, or
  * `../../frontend/dist` relative to `backend/nunet_api`
* Failure to locate the SPA directory results in a runtime exception at startup – this is deliberate to catch missing builds in CI.
* GZip is enabled for responses ≥ 1 KB to improve frontend load times.

---

## 6. Command Execution & Shell Access

Several routers execute system commands:

* `/dms` endpoints call `nunet` via `run_dms_command_with_passphrase` and may invoke shell scripts through `subprocess.run`.
* Template and status helpers may spawn subprocesses for log tailing or Docker introspection; review each call site before expanding functionality.

When introducing new shell-dependent endpoints:

1. Prefer to implement helpers in `backend/modules` and import them.
2. Ensure any shell commands validate and sanitize inputs (no direct string concatenation).
3. Consider privilege requirements – many commands leverage `sudo -n`. Update deployment sudoers if necessary, and document the requirement.

---

## 7. Common Patterns

* **Error Handling** – Always return `{"status": "...", "message": "..."}` or raise `HTTPException(detail=...)` for errors. Managers follow the same pattern.
* **Caching** – DMS status/resource queries use in-memory caches with TTL to reduce CLI calls. Set `refresh=true` query param to force refresh.
* **File Resolution** – When returning filesystem content (templates, logs), code safeguards against path traversal and ensures the file exists before reading.
* **WebSockets** – Real-time operations (DMS updates, PTY bridging) use `run_pty_ws` or custom async loops. Any new WS route should follow the same pattern for auth and resource cleanup.

---

## 8. Directory Layout

```
backend/nunet_api/
├── adapters.py          # Normalization helpers (status parsing, ANSI stripping)
├── main.py              # FastAPI app factory, router registration, SPA mount
├── routers/             # Area-specific routers (auth, dms, ensemble, etc.)
├── schemas.py           # Pydantic models shared by routers
├── security.py          # Auth helpers (token handling, password hashing)
├── utils/
│   └── pty_bridge.py    # Shared PTY-to-WebSocket bridge
└── requirements.txt     # Python deps for the API
```

The routers import helper modules exclusively from `backend/modules`. Keep that contract intact.

---

## 9. Extending the API

When adding a new endpoint:

1. **Identify the module you need** under `backend/modules`. Add new helpers there if necessary.
2. **Create a router or extend an existing one**. Routers should be area-focused.
3. **Add Pydantic models** (`schemas.py`) for request/response bodies.
4. **Protect the endpoint** by adding `dependencies=protected` unless it must be unauthenticated.
5. **Update this README** – document the new route and its dependencies.
6. **Update the frontend** if the API change is frontend-facing (`frontend/src/api/...`).
7. **Tests** – add unit/integration tests (`backend/tests/`) for non-trivial logic.

---

## 10. Logging & Observability

* FastAPI uses the standard logging configuration; structured logging from managers is done via Python’s `logging` module.
* DMS log retrieval routes (e.g., `/dms/logs`, `/dms/logs/structured`) use `journalctl` or file tailing under the hood.
* Add new log streams carefully: follow the existing patterns to avoid leaking credentials or flooding the client.

---

## 11. Known External Requirements

Make sure the following commands are available on the appliance for the API to work end-to-end:

| Command | Used for |
| --- | --- |
| `nunet` | All DMS interactions |
| `docker` | DDNS/Docker endpoints |
| `systemctl` | DMS service management |
| `journalctl` | Log retrieval |
| `curl`, `dig`, `wget`, `apt` | Onboarding scripts, DDNS registration, updates |
| `sudo` | Many commands require passwordless sudo for the `ubuntu` user (see deployment sudoers file) |

When deploying to a new environment, verify sudo rules listed in the comments of `requirements.txt`.

---

## 12. Quick Reference: Endpoints by Category

### Auth
* `POST /auth/login`
* `GET /auth/status`
* `POST /auth/setup`

### DMS
* `GET /dms/version`, `/install`, `/status`, `/status/full`, `/status/combined`
* `POST /dms/restart`, `/onboard`, `/offboard`, `/init`, `/update`
* `GET /dms/logs`, `/logs/structured`, `/peers/connected`

### System Info
* `GET /sys/local-ip`, `/public-ip`, `/appliance-version`, `/ssh-status`, `/docker/containers`

### Deployments / Ensembles
* `GET /ensemble/deployments`, `/deployments/running`, `/deployments/{id}/status`
* `GET /ensemble/deployments/{id}/manifest/raw`, `/file`, `/logs`, `/allocations`
* `POST /ensemble/deployments` (submit), `/deployments/{id}/shutdown`
* Template management: `GET /ensemble/templates`, `POST /ensemble/templates/copy`, `/upload`, `/forms`, `/schema`
* `POST /ensemble/deploy/from-template`

### Organizations / Onboarding
* `GET /organizations/known`, `/joined`, `/steps`, `/status`
* `POST /organizations/select`, `/wormhole`, `/join/submit`, `/join/process`
* `POST /organizations/process` (handles post-approval payload)
* `POST /organizations/reset`

### Payments
* `GET /payments/config`, `/payments/list_payments`
* `POST /payments/report_to_dms`

---

Keep this README up to date whenever you introduce new routers, change prefixes, or adjust security assumptions. A clean, well-documented backend makes iterating on the appliance much easier. 🚀
