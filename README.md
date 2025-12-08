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

---

## `deploy/scripts/devctl.sh` Overview

`devctl` is the primary helper script used during development, packaging, and testing. It wraps common tasks for both the backend and frontend. Available subcommands include (run `./deploy/scripts/devctl.sh help` for the latest list):

| Command | Purpose |
| --- | --- |
| `dev up` | Start the FastAPI backend (with `uvicorn`) and the frontend dev server. Uses a Python venv under `deploy/.dev-venv` and a Node.js install under `frontend`. |
| `dev test` | Run backend unit tests (`pytest`) and any other configured checks. |
| `dev lint` | Example placeholder for linting (add your linters or formatters here). |
| `build backend` | Build backend distributables (e.g., wheel or PEX) – adjust to your packaging needs. |
| `build frontend` | Run `pnpm install` and `pnpm run build` to produce the production bundle under `frontend/dist`. |
| `clean` | Remove temporary build artifacts, virtual environments, cached dependencies, etc. |

Internally, the script performs a few key tasks:

* Ensures the Python virtual environment exists and installs `backend/nunet_api/requirements.txt`
* Ensures frontend dependencies are installed (`pnpm install`)
* Starts/stops the appropriate processes depending on the subcommand
* Provides a single entrypoint for CI/CD automation and local workflows

> **Tip:** Run `./deploy/scripts/devctl.sh help` to see the most up-to-date list of commands, as the script evolves over time.

---

## Repo Layout

```
.
├── backend/
│   ├── modules/           # Shared helper modules (documented in modules/README.md)
│   └── nunet_api/         # FastAPI application (documented in nunet_api/README.md)
├── deploy/
│   └── scripts/
│       └── devctl.sh      # Development CLI helper
├── frontend/              # React/Vite SPA
└── README.md              # This document
```

---

## Getting Started

1. **Clone the repo** and make sure you have Python 3.10+ and Node.js 22.x installed (with Corepack so `pnpm@10.4.0` is available).
2. **Bootstrap the dev environment** by running `./deploy/scripts/devctl.sh dev up` (this creates virtual envs, installs dependencies, and starts both backend and frontend).
3. **Open the API** – once running, the backend exposes `http://127.0.0.1:8080` (default) and the frontend runs on `http://127.0.0.1:5173` (or whichever Vite port is configured).
4. **Explore the documentation** linked above to understand module responsibilities and API endpoints.

---

## Runtime Paths & Config

- Default writable locations (dev + prod): ensembles at `/home/ubuntu/ensembles`, contracts at `/home/ubuntu/contracts`, appliance data at `/home/ubuntu/nunet/appliance`, DMS caps under `/home/ubuntu/.nunet` and `/home/nunet/.nunet`, DMS config at `/home/nunet/config/dms_config.json`.
- `.env` is optional in dev; if present it can override ports or paths. If omitted, the fixed defaults above apply (no fallbacks to repo-relative paths).

## Logs

- Dev (`devctl dev up`): backend/frontend logs live under `.devctl/run/backend.log` and `.devctl/run/frontend.log` in the repo.
- Prod (deb install): backend logs via `journalctl -u nunet-appliance-web -f`; DMS logs at `/home/ubuntu/nunet/appliance/logs/nunet-dms.log`.

---

## Contributing

* Keep `backend/modules` in sync with the API – only helpers needed by the routers should live there.
* Update the backend and frontend READMEs whenever you add or remove functionality.
* Prefer introducing new functionality via the FastAPI routers rather than reviving legacy menu scripts.
* Run `./deploy/scripts/devctl.sh dev test` before opening a merge request.

Happy hacking! 🚀
