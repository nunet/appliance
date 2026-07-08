# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

NuNet Appliance is a full-stack web application for managing a distributed computing node. It consists of a FastAPI backend, a React/TypeScript frontend, and Debian package build tooling.

**Integrated development** (canonical): `./deploy/scripts/nunet-web-mode.sh` (`dev-on`, `rebuild`, `dev-off`) — real `nunet-appliance-web` on `https://localhost:8443`.

**Packaging / local bootstrap**: `./deploy/scripts/devctl.sh` (`setup`, `build`, `install`, `prod up`, …) — does not start split dev servers.

## Common Commands

```bash
./deploy/scripts/nunet-web-mode.sh dev-on    # repo venv + frontend/dist via systemd
./deploy/scripts/nunet-web-mode.sh rebuild
./deploy/scripts/devctl.sh setup             # .venv + deps only (unit pytest)
./deploy/scripts/devctl.sh build 1.2.3
./deploy/scripts/devctl.sh status
```

`devctl` does **not** include a test subcommand; use pytest and Playwright per root `README.md` and `frontend/README.md`. **`dev up` / `dev down` are removed** (formerly split Vite + API).

Backend tests (pytest), from **repository root** (uses `.venv`, `PYTHONPATH`, installs `pytest`/`httpx` if needed):
```bash
./deploy/scripts/run-pytest.sh
./deploy/scripts/run-pytest.sh backend/tests/test_nunet_api_api.py
./deploy/scripts/run-pytest.sh backend/tests/test_nunet_api_api.py::test_health_endpoint
```

### Frontend (standalone)
```bash
cd frontend
pnpm install
pnpm run dev    # Vite dev server on http://localhost:5173
pnpm run build  # Production bundle to frontend/dist
pnpm run lint   # ESLint
pnpm e2e        # Playwright headless (DEV ON, https://localhost:8443)
pnpm e2e:ui     # Playwright UI mode
```

### Default Ports
- Integrated web (DEV ON / production): `8443` (HTTPS)
- Optional Vite-only UI: `5173` (`cd frontend && pnpm run dev` — not used for integration/E2E)

## Architecture

### Backend (`backend/`)

**Entry point:** `backend/nunet_api/main.py`

FastAPI app with routers mounted per domain. All routers import only from `backend/modules/` — no cross-router imports.

**Routers** (`backend/nunet_api/routers/`):
| Router | Prefix | Purpose |
|--------|--------|---------|
| `auth.py` | `/auth` | Login, setup, token refresh |
| `dms.py` | `/dms` | DMS service lifecycle, contracts, payments |
| `sys.py` | `/sys` | System info (IP, version, SSH, Docker) |
| `ensemble.py` | `/ensemble` | Deployment CRUD and templates |
| `organizations.py` | `/organizations` | Onboarding wizard and join flow |
| `contracts.py` | `/contracts` | Contract state and approval |
| `payments.py` | `/payments` | Payment listings and confirmations |
| `filesystem.py` | `/filesystem` | File operations |
| `upnp.py` | `/upnp` | UPnP port forwarding |
| `appliance.py` | `/appliance` | Appliance metadata |

**Modules** (`backend/modules/`): Business logic layer. Key modules:
- `dms_manager.py` — High-level DMS orchestration
- `dms_utils.py` — Low-level DMS CLI execution with TTL caching; pass `?refresh=true` to bypass cache
- `ensemble_manager_v2.py` — Deployment lifecycle management
- `onboarding_manager.py` — Org onboarding flow state machine (see section below)
- `organization_manager.py` — Wraps shell scripts for org operations

### Organization Onboarding Flow

Three components collaborate to deliver capability tokens, certificates, and contracts to the appliance:

```
Appliance (organizations router + OnboardingManager)
    ↕ HTTP (org's onboarding_api_url from known_orgs.json)
Organization Manager (Django API — external, per-org)
    ↕ HTTP (API_BASE_URL / API_KEY)
onboarding-worker (separate repo — capability signer + orchestrator)
```

**Appliance side** (`routers/organizations.py` + `modules/onboarding_manager.py`):

1. **`POST /organizations/join/submit`** — Collects the join form, ensures the local DMS node is onboarded (`ensure_pre_onboarding`), attaches hardware resource info, then POSTs to `{onboarding_api_url}/onboarding/submit/`. Stores the returned `request_id` and `status_token` in state.
2. **`GET /organizations/join/poll`** — Frontend polls this endpoint. The router calls `api_check_status(request_id, status_token)` → `{onboarding_api_url}/onboarding/status/{request_id}/`. When the org manager's status reaches key transitions, the router drives the next local step (e.g., applying caps, confirming receipt).
3. **`POST /organizations/join/process`** — Manually triggered step that applies a returned payload (capability tokens, certs, contracts) to the local DMS using `process_post_approval_payload`.
4. **Contract-enabled callbacks** — After receiving a contract DID from the org manager, the appliance calls back:
   - `api_confirm_caps(request_id, status_token, "contract"|"deployment")` → `POST {api_url}/onboarding/confirm-caps/{id}/`
   - `api_contract_received(...)` → `POST {api_url}/onboarding/contract-received/{id}/`
   - `api_contract_signed(...)` → `POST {api_url}/onboarding/contract-signed/{id}/`

**Onboarding state steps** (stored in `~/.nunet/appliance/onboarding_state.json`):
`init` → `select_org` → `collect_join_data` → `submit_data` → `join_data_sent` → `pending_authorization` → `contract_caps_ready` → `contract_caps_applied` → `contract_created` → `contract_received` → `contract_signed` → `deployment_caps_ready` → `deployment_caps_applied` → `complete`

**`onboarding_api_url`** is resolved per-org from `known_orgs.json` (bundled in `known_orgs/`). Each org entry carries the URL under `onboarding_api_url` or `api_url`.

**onboarding-worker side** (see `../onboarding-worker/`): Polls the org manager for available requests, claims them, and drives capability signing and contract creation across five phases. The worker does **not** communicate directly with the appliance — it only talks to the org manager API, which the appliance also polls.

**Authentication:** JWT Bearer tokens. All endpoints require auth except `/auth`, `/health`, `/setup`, `/login`. Token validation is via the `require_auth` dependency in `security.py`. Passwords are bcrypt-hashed in `~/.nunet/appliance/admin_credentials.json`.

**API response shape:** All responses follow `{"status": "...", "message": "..."}`.

**System dependencies** the backend calls as subprocesses: `nunet` (DMS CLI), `docker`, `systemctl`, `journalctl`, `curl`, `dig`. Requires passwordless `sudo` for the `ubuntu` user.

### Frontend (`frontend/src/`)

**Entry point:** `frontend/src/main.tsx`

React 19 SPA using hash-based routing (React Router v7). The FastAPI server mounts the built frontend at `/`.

**Key directories:**
- `api/` — Axios-based API clients, one file per backend router
- `pages/` — Route-mapped page components
- `components/` — Reusable React components (sidebar, domain-specific widgets)
- `hooks/` — `useAuth` (JWT token management) and other custom hooks
- `stores/` — Zustand global state
- `types/` — TypeScript interfaces matching backend schemas
- `lib/` — Zod validators and utility helpers

**Stack:** React Query (server state + caching), Radix UI (headless components), TailwindCSS 4, Lucide icons, Recharts (analytics), Zod (validation).

### Build & Packaging (`deploy/`)

CI builds two Debian packages via GitLab CI (`.gitlab-ci.yml`):
- `nunet-appliance-base` — System dependencies
- `nunet-appliance-web` — API + frontend bundle

Versions are extracted from git tags (e.g., `v1.2.3`, `r1.2.3`). The pipeline builds for both `x86_64` and `ARM64`.

**Data directories at runtime:**
- `/home/ubuntu/ensembles/` — Deployment manifests
- `/home/ubuntu/contracts/` — Contract definitions
- `/home/ubuntu/.nunet/appliance/` — Appliance state (credentials, onboarding)
- `/home/nunet/config/dms_config.json` — DMS configuration

## Development Requirements

- Python 3.10+
- Node.js 22.x
- pnpm 10.4.0 (managed via Corepack)
