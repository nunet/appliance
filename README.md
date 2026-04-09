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

## `deploy/scripts/devctl.sh` Overview

`devctl` is the primary helper script used during development and packaging. Run `./deploy/scripts/devctl.sh` with no arguments (or `help`) to print the current command list—it matches what is implemented in `deploy/scripts/devctl.sh` (for example `dev up` / `dev down`, `prod up` / `prod down`, `build`, `install`, `rollback`, `status`, `logs`, `ps`, `doctor`).

Internally, `dev up` ensures a Python venv (default `$ROOT/.venv`), installs `backend/nunet_api/requirements.txt`, installs frontend deps with pnpm, and starts the backend and Vite dev servers.

**Backend tests** are not run by `devctl`. From the **repository root**, use **`deploy/scripts/run-pytest.sh`**: it activates **`$ROOT/.venv`** (same default as `devctl` / `nunet-web-mode`), sets **`PYTHONPATH`** for `backend.*` and `modules.*`, installs **`pytest`** and **`httpx`** into that venv if missing, then runs pytest.

```bash
./deploy/scripts/run-pytest.sh
./deploy/scripts/run-pytest.sh -q --tb=short
./deploy/scripts/run-pytest.sh backend/tests/test_environment_profile.py -v
```

See `frontend/README.md` for Cypress E2E. The `.cursor/rules/testing.mdc` rule summarizes both.

### `deploy/scripts/nunet-web-mode.sh` Overview

Use this script when testing against the integrated service on `https://localhost:8443`:

```bash
./deploy/scripts/nunet-web-mode.sh dev-on    # repo backend+frontend via systemd drop-in
./deploy/scripts/nunet-web-mode.sh rebuild   # refresh venv + frontend build, restart service
./deploy/scripts/nunet-web-mode.sh status    # show active service/unit wiring
./deploy/scripts/nunet-web-mode.sh dev-off   # return to packaged systemd defaults
```

`dev-on` writes a systemd drop-in override so the service uses repo paths (`backend/`, `.venv`, `frontend/dist`) instead of packaged paths. `dev-off` removes that override.

---

## Repo Layout

```
.
├── backend/
│   ├── modules/           # Shared helper modules (documented in modules/README.md)
│   └── nunet_api/         # FastAPI application (documented in nunet_api/README.md)
├── deploy/
│   └── scripts/
│       ├── devctl.sh           # Development CLI helper
│       ├── nunet-web-mode.sh   # dev-on/off + rebuild/status for real web service
│       └── run-pytest.sh       # Backend pytest (venv + PYTHONPATH + optional deps)
├── frontend/              # React/Vite SPA
└── README.md              # This document
```

---

## Getting Started

1. **Clone the repo** and make sure you have Python 3.10+ and Node.js 22.x installed (with Corepack so `pnpm@10.33.0` is available).
2. **Bootstrap the dev environment** by running `./deploy/scripts/devctl.sh dev up` (this creates virtual envs, installs dependencies, and starts both backend and frontend).
3. **Open the API** – once running, the backend exposes `http://127.0.0.1:8080` (default) and the frontend runs on `http://127.0.0.1:5173` (or whichever Vite port is configured).
4. **Explore the documentation** linked above to understand module responsibilities and API endpoints.

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

- Dev (`devctl dev up`): backend/frontend logs live under `.devctl/run/backend.log` and `.devctl/run/frontend.log` in the repo.
- Prod (deb install): backend logs via `journalctl -u nunet-appliance-web -f`; DMS logs at `/home/ubuntu/nunet/appliance/logs/nunet-dms.log`.

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
* Run `./deploy/scripts/run-pytest.sh` from the repo root (and any relevant Cypress specs) before opening a merge request. For integrated-service testing, switch to repo-backed mode with **`./deploy/scripts/nunet-web-mode.sh dev-on`**, then run **`./deploy/scripts/nunet-web-mode.sh rebuild`** after frontend changes so the running bundle matches the repo.

Happy hacking! 🚀

