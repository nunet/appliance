# NuNet Appliance Repository

This repository bundles everything needed to run the NuNet appliance:

* backend FastAPI application and helper modules (`backend/`)
* frontend SPA (`frontend/`)
* deployment scripts (`deploy/`)
* supporting documentation

If you are familiar with the legacy menu / Flask stack, note that almost all of that code has been removed. What remains is the minimum required for the new FastAPI backend and the React dashboard.

---

## Quick Links

| Area | Location | Description |
| --- | --- | --- |
| Backend helper modules | [`backend/modules/README.md`](backend/modules/README.md) | Inventory of Python helper modules and how each ties into the API. |
| FastAPI application | [`backend/nunet_api/README.md`](backend/nunet_api/README.md) | Detailed guide for the REST API (routers, authentication, dependencies). |
| Frontend | `frontend/` | React/Vite SPA that consumes the API; see comments in source files and the dashboard components. |
| Deployment tooling | [`deploy/scripts/devctl.sh`](deploy/scripts/devctl.sh) | Main CLI entrypoint for local development and deployments (see below). |
| Integrated web mode (systemd) | [`deploy/scripts/nunet-web-mode.sh`](deploy/scripts/nunet-web-mode.sh) | **`dev-on` / `dev-off` / `rebuild` / `status`** — switch the real web unit between packaged and repo-backed execution, rebuild frontend, and inspect active unit config. |
| Dependency security | [`docs/dependency-security.md`](docs/dependency-security.md) | Lockfile, audit gating, and supply-chain hardening policy. |
| Dependency update runbook | [`docs/dependency-update-procedure.md`](docs/dependency-update-procedure.md) | Step-by-step procedure for adding/updating dependencies safely. |

---

## Development: `nunet-web-mode.sh` vs `devctl.sh`

Two scripts serve different roles. **Integration tests, contract tests, and Playwright E2E** use the **integrated** stack only (`https://localhost:8443` with **DEV ON**), not a separate Vite + API split.

| Script | Role | Typical commands |
|--------|------|------------------|
| [`nunet-web-mode.sh`](deploy/scripts/nunet-web-mode.sh) | Switch the **real** `nunet-appliance-web` systemd unit to repo-backed code (`backend/`, `.venv`, `frontend/dist`) | `dev-on`, `rebuild`, `status`, `dev-off` |
| [`devctl.sh`](deploy/scripts/devctl.sh) | **Packaging/ops** and local bootstrap **without starting servers** | `setup`, `build`, `install`, `prod up`, `status`, `doctor` |

### `nunet-web-mode.sh` (canonical for live app + integration/E2E)

```bash
./deploy/scripts/nunet-web-mode.sh dev-on    # venv + frontend build + systemd override
./deploy/scripts/nunet-web-mode.sh rebuild   # refresh venv/dist and restart
./deploy/scripts/nunet-web-mode.sh status    # ExecStart, drop-in, environment
./deploy/scripts/nunet-web-mode.sh dev-off   # packaged unit defaults
```

`dev-on` writes `/etc/systemd/system/nunet-appliance-web.service.d/override.conf` so gunicorn runs from the repo venv and serves `frontend/dist` on port **8443** (same origin for SPA and API).

### `devctl.sh` (venv bootstrap + DEB workflow)

```bash
./deploy/scripts/devctl.sh setup       # .venv + pip (+ optional pnpm); no HTTP servers
./deploy/scripts/devctl.sh test-deps   # optional OS libs for Playwright (sudo)
./deploy/scripts/devctl.sh build 1.2.3
./deploy/scripts/devctl.sh install
```

For unit pytest only, `devctl setup` is enough. For Vite HMR alone: `cd frontend && pnpm run dev` (not used for integration/E2E).


## Testing (DEV ON pyramid)

All integration-style tests target the **integrated web service** via **`APPLIANCE_BASE_URL`** (default `https://localhost:8443`) with **`nunet-web-mode.sh dev-on`** on the appliance host. Copy **`.env.test.example`** → **`.env.test`** and set **`APPLIANCE_ADMIN_PASSWORD`** (and **`APPLIANCE_BASE_URL`** when tests run from another machine or a container).

| Tier | Command | What it covers |
|------|---------|----------------|
| **pytest unit** (default) | `./deploy/scripts/run-pytest.sh` | Fast tests with module stubs |
| **pytest integration** | `./deploy/scripts/run-pytest.sh -m integration` | Live API routers (`backend/tests/integration/`) |
| **pytest contract** | `./deploy/scripts/run-pytest.sh -m contract` | OpenAPI / Schemathesis (safe HTTP verbs) |
| **Playwright (CI parity)** | `./deploy/scripts/run-playwright-ci.sh` | Browser journeys in Docker (`frontend/playwright/`) |
| **Playwright (native)** | `cd frontend && pnpm e2e` | Same specs on the host after `playwright install` |

```bash
./deploy/scripts/run-pytest.sh -q

# Bring up DEV ON (from repo root)
./deploy/scripts/nunet-web-mode.sh dev-on
./deploy/scripts/nunet-web-mode.sh rebuild

set -a && source .env.test && set +a
./deploy/scripts/run-pytest.sh -m integration
./deploy/scripts/run-pytest.sh -m contract
./deploy/scripts/run-playwright-ci.sh
```

CI: see **`docs/ci-appliance-runner.md`** (appliance host for DEV ON/OFF; integration and Playwright in containers).

Details: **`.cursor/rules/testing.mdc`** and **`frontend/README.md`** (Playwright quick start).

---

## Repo Layout

```
.
├── backend/
│   ├── modules/                 # Shared helper modules (documented in modules/README.md)
│   └── nunet_api/               # FastAPI application (documented in nunet_api/README.md)
├── deploy/
│   └── scripts/
│       ├── devctl.sh            # Development CLI helper
│       ├── nunet-web-mode.sh    # dev-on/off + rebuild/status for real web service
│       ├── run-pytest.sh        # Backend pytest (venv + PYTHONPATH + optional deps)
│       └── run-playwright-ci.sh # Playwright E2E (Docker / CI parity)
├── frontend/                    # React/Vite SPA
└── README.md                    # This document
```

---

## Getting Started

1. **Clone the repo** on an appliance (or equivalent VM) with Python 3.10+ and Node.js 22.x (Corepack for `pnpm`).
2. **Bootstrap tooling** (no servers): `./deploy/scripts/devctl.sh setup`
3. **Run the integrated web app**: `./deploy/scripts/nunet-web-mode.sh dev-on && ./deploy/scripts/nunet-web-mode.sh rebuild` — open **`https://localhost:8443`**
4. **Unit tests** (isolated, no DEV ON): `./deploy/scripts/run-pytest.sh`
5. See linked READMEs for API modules and frontend structure.

## VirtualBox Log Sharing

In VirtualBox, go to `Settings -> Shared Folders -> Add Share` and fill out the form:

- Folder Path: *user's choice*
- Mount Point: `/home/nunet/logs`
- Check Auto-mount
- Check Make Machine-permanent

File `nunet-dms.log` will appear in the *user's choice* folder.

---

## Runtime Paths & Config

- Default writable locations (dev + prod): ensembles at `/home/ubuntu/ensembles`, contracts at `/home/ubuntu/contracts`, appliance data at `/home/ubuntu/nunet/appliance`, DMS caps under `/home/ubuntu/.nunet` and `/home/nunet/.nunet`, DMS config at `/home/nunet/config/dms_config.json`.
- `.env` is optional in dev; if present it can override ports or paths. If omitted, the fixed defaults above apply (no fallbacks to repo-relative paths).

## Logs

- Integrated web (DEV ON or packaged): `journalctl -u nunet-appliance-web -f` or `./deploy/scripts/devctl.sh logs`
- DMS: `/home/ubuntu/nunet/appliance/logs/nunet-dms.log`

---

## Dependency Security

- Frontend installs are locked with `pnpm-lock.yaml` and must use `pnpm install --frozen-lockfile` in build/dev scripts.
- CI includes dedicated dependency gates for both Python (`pip-audit`) and frontend (`pnpm audit`) and blocks builds when vulnerabilities are detected.
- See [`docs/dependency-security.md`](docs/dependency-security.md) for update workflow and emergency override guidance.

---

## Contributing

* Keep `backend/modules` in sync with the API – only helpers needed by the routers should live there.
* Update the backend and frontend READMEs whenever you add or remove functionality.
* Prefer introducing new functionality via the FastAPI routers rather than reviving legacy menu scripts.
* Run `./deploy/scripts/run-pytest.sh` and relevant Playwright specs (`frontend/`, `pnpm e2e`) before opening a merge request. Use **`./deploy/scripts/nunet-web-mode.sh dev-on`** + **`rebuild`** so the live service matches the repo.

Happy hacking! 🚀

