# React + TypeScript + Vite

This template provides a minimal setup to get React working in Vite with HMR and some ESLint rules.

Currently, two official plugins are available:

- [@vitejs/plugin-react](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react) uses [Babel](https://babeljs.io/) for Fast Refresh
- [@vitejs/plugin-react-swc](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react-swc) uses [SWC](https://swc.rs/) for Fast Refresh

## Expanding the ESLint configuration

If you are developing a production application, we recommend updating the configuration to enable type-aware lint rules:

```js
export default tseslint.config([
  globalIgnores(['dist']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      // Other configs...

      // Remove tseslint.configs.recommended and replace with this
      ...tseslint.configs.recommendedTypeChecked,
      // Alternatively, use this for stricter rules
      ...tseslint.configs.strictTypeChecked,
      // Optionally, add this for stylistic rules
      ...tseslint.configs.stylisticTypeChecked,

      // Other configs...
    ],
    languageOptions: {
      parserOptions: {
        project: ['./tsconfig.node.json', './tsconfig.app.json'],
        tsconfigRootDir: import.meta.dirname,
      },
      // other options...
    },
  },
])
```

You can also install [eslint-plugin-react-x](https://github.com/Rel1cx/eslint-react/tree/main/packages/plugins/eslint-plugin-react-x) and [eslint-plugin-react-dom](https://github.com/Rel1cx/eslint-react/tree/main/packages/plugins/eslint-plugin-react-dom) for React-specific lint rules:

```js
// eslint.config.js
import reactX from 'eslint-plugin-react-x'
import reactDom from 'eslint-plugin-react-dom'

export default tseslint.config([
  globalIgnores(['dist']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      // Other configs...
      // Enable lint rules for React
      reactX.configs['recommended-typescript'],
      // Enable lint rules for React DOM
      reactDom.configs.recommended,
    ],
    languageOptions: {
      parserOptions: {
        project: ['./tsconfig.node.json', './tsconfig.app.json'],
        tsconfigRootDir: import.meta.dirname,
      },
      // other options...
    },
  },
])
```

## E2E testing (Cypress)

End-to-end tests are driven by Cypress. **This is a Node.js toolchain only** — it does **not** use the repo Python venv (that venv is for **`./deploy/scripts/run-pytest.sh`** and the API). Install JS deps under **`frontend/`** as below.

### Seeing what ran: timings, video, and deeper profiling

**Built-in timing in `real-appliance-dashboard.cy.ts`:** the spec logs **`[timing] …`** lines (ms from flow start) at milestones: login page ready, after Sign in, hash is `/#/`, **`Peer ID:`** visible, **`dashboard-main-status`** card, each resource card (or **skipped** if the UI hides them), then **`total_flow`**. Those lines appear in:

- the **terminal** (via `cy.task("log")`, same as other `logStep` output),
- the **Cypress command log** in the runner UI (`cy.log`).

**Watch the browser:** `pnpm exec cypress run --headed --browser electron --spec cypress/e2e/real-appliance-dashboard.cy.ts` (or `cypress open` and run the spec).

**Record a run:** set `video: true` in `cypress.config.ts` (or pass `--config video=true`) to capture video under `frontend/cypress/videos/` (add to `.gitignore` if not already).

**Network / React timing:** use **headed** run, open DevTools (F12) → **Network** (waterfall per request) or **Performance** (record while the test runs). Cypress does not replace Chrome’s profiler; the spec timings are **wall-clock to visible elements**, not per-component React render cost.

**Machine-readable reports:** add a reporter (e.g. Mochawesome) in `cypress.config.ts` if you need HTML/JSON output for CI.

### Troubleshooting: Cypress still waits for port 5173

**`CYPRESS_BASE_URL` overrides** the default in `cypress.config.ts`. If you previously created **`frontend/.env.e2e`** from an older `.env.e2e.example`, it may still set `CYPRESS_BASE_URL=http://localhost:5173`. Either update those lines to **`https://…:8443`** (and matching `CYPRESS_BACKEND_BASE_URL`) or remove them and rely on defaults. When Cypress starts, the console prints **`[cypress.config] baseUrl:`** so you can see which value is in effect.

### Quick start (real appliance integration spec)

After changing the React app, from the **repo root** run **`./deploy/scripts/nunet-web-mode.sh rebuild`** so **`https://localhost:8443`** serves the new bundle (then run Cypress). To **rebuild automatically before Cypress**, set **`CYPRESS_REBUILD_FRONTEND=true`** in **`.env.e2e`** (or run **`pnpm cy:run:e2e:rebuild`**). That runs the same script from **`cypress.config.ts`** (`before:run`); **`sudo`** may prompt for **`systemctl restart`**.

From **`frontend/`**:

```bash
test -f .env.e2e || cp .env.e2e.example .env.e2e
# Edit .env.e2e: CYPRESS_BASE_URL, CYPRESS_BACKEND_BASE_URL (same origin), CYPRESS_ADMIN_PASSWORD, CYPRESS_VERIFY_SSL=false for self-signed HTTPS

npx --yes pnpm@10.4.0 install --frozen-lockfile
./scripts/run-cypress.sh run --browser electron --spec cypress/e2e/real-appliance-dashboard.cy.ts
```

- **`pnpm` not installed globally?** You do not need it: **`npx --yes pnpm@10.4.0`** downloads a pinned pnpm and installs from **`pnpm-lock.yaml`**. **`./scripts/run-cypress.sh`** runs the **local** `node_modules/.bin/cypress` when present.
- **`source .env.e2e` failed:** create the file first (`cp .env.e2e.example .env.e2e`).

End-to-end tests can target the **Vite dev server** (split stack) or the **real web service** that serves the **production-built** SPA and the API from the **same origin** (recommended for integration-style runs).

**Integration vs isolated UI:** **`cypress/e2e/real-appliance-dashboard.cy.ts`** exercises the **real** appliance: browser login form, JWT, and dashboard data from the live API (no mocks for that flow). Other specs under `cypress/e2e/` use **`cy.intercept`** to stub backends for focused UI checks—treat them as component-style E2E, not substitutes for the integration spec.

### E2E against the real web service (production bundle)

Use this when you want Cypress to hit the same deployment as users: the FastAPI app serves `frontend/dist` and the API on one host/port (for example `nunet-appliance-web` via systemd).

**Why the env is different from dev:** In a production build (`pnpm run build`), the SPA uses **relative** API URLs (`api.ts` uses an empty axios `baseURL`). The browser must load the app from the **same origin** as the API. Cypress must therefore use **one** base URL for both the UI and the backend helper calls in `loginOrInitialize` (`cy.request` to `/auth/status`, `/auth/token`, etc.).

#### Recommended control flow: `nunet-web-mode.sh`

From repo root, use:

```bash
./deploy/scripts/nunet-web-mode.sh dev-on
./deploy/scripts/nunet-web-mode.sh rebuild
./deploy/scripts/nunet-web-mode.sh status
./deploy/scripts/nunet-web-mode.sh dev-off
```

- `dev-on` switches the real systemd web service to repo-backed execution (backend from `.venv`, frontend from `frontend/dist`).
- `rebuild` refreshes the frontend bundle (and venv deps) and restarts the service before E2E.
- `status` confirms the active unit/drop-in/ExecStart wiring.
- `dev-off` restores packaged unit defaults.

#### Live UI switched to repo directories (recommended for “real” E2E)

This is the usual case when you have pointed the **live** service at your git checkout—for example a systemd drop-in or helper (often described as **nunet-web-mode** / **dev-on**) so **`NUNET_STATIC_DIR`** (or equivalent) serves **`$APPLIANCE_ROOT/frontend/dist`** and the backend runs from the same repo layout. The dashboard URL is unchanged (same port and TLS as production, e.g. `https://host:8443`); only the files on disk come from the clone.

1. **Build and reload** the integrated UI from the **repository root**: **`./deploy/scripts/nunet-web-mode.sh rebuild`** — runs **`pnpm install` + `pnpm run build`** in **`frontend/`** and **restarts** **`nunet-appliance-web.service`** when active (so new **`frontend/dist`** is what the service serves).
2. If you only build by hand: `cd frontend && npx --yes pnpm@10.4.0 run build`, then restart the web unit yourself.
3. **Cypress env:** set **`CYPRESS_BASE_URL`** and **`CYPRESS_BACKEND_BASE_URL`** to that **same** `https://…` origin (see **`frontend/.env.e2e.example`**). Use **`CYPRESS_VERIFY_SSL=false`** for the appliance’s self-signed cert; run **`pnpm cy:run:e2e`** from **`frontend/`** so `.env.e2e` is loaded and Node trusts the cert for `cy.request`.

You can run Cypress **on the appliance** or **from another machine**; use a hostname or IP that reaches the web UI (firewall allowing HTTPS to that port).

#### Flow

1. **Build the frontend** from the repo root (or from `frontend/`):

   ```bash
   cd frontend
   corepack prepare pnpm@10.4.0 --activate
   pnpm install --frozen-lockfile
   pnpm run build
   ```

   Output goes to `frontend/dist/`.

2. **Serve that build** from the checkout: **`./deploy/scripts/nunet-web-mode.sh rebuild`** (or restart **`nunet-appliance-web`** after a manual `pnpm run build`) so **`NUNET_STATIC_DIR`** → **`frontend/dist`** is what users hit.

3. **Confirm the appliance URL** you will use in the browser (scheme + host + port), for example `https://192.168.1.10:8443` or `https://localhost:8443`.

4. **Configure `.env.e2e`** (copy from `.env.e2e.example` if needed):

   - **`CYPRESS_BASE_URL`** — full URL of the web UI (same as the service above).
   - **`CYPRESS_BACKEND_BASE_URL`** — set to the **same** value as `CYPRESS_BASE_URL` so `loginOrInitialize` and other `cy.request` calls target the same API origin as the built app.
   - **`CYPRESS_ADMIN_PASSWORD`** — the admin password configured on that appliance (must match the password in `~/.secrets/admin_credentials.json` on the host).
   - **`CYPRESS_VERIFY_SSL=false`** — often required for the appliance’s self-signed HTTPS certificate.
   - Optional: **`CYPRESS_SETUP_TOKEN_PATH`**, **`CYPRESS_SETUP_TOKEN`** if the appliance has no admin password yet (first-boot setup).

5. **Run Cypress** (from `frontend/`), with the env file loaded:

   ```bash
   pnpm cy:run:e2e
   ```

   Equivalent manual form:

   ```bash
   set -a && source .env.e2e && set +a
   pnpm exec cypress run --browser electron
   ```

   `pnpm cy:run:e2e` / `pnpm cy:open:e2e` call **`scripts/run-cypress.sh`**, which sources `.env.e2e` and, when `CYPRESS_VERIFY_SSL=false`, sets `NODE_TLS_REJECT_UNAUTHORIZED=0` for Node-side `cy.request` against self-signed HTTPS.

   Or use the Docker runner (it sources `.env.e2e` by default):

   ```bash
   ./scripts/run-e2e-docker.sh
   ```

   Ensure the machine running Cypress can reach `CYPRESS_BASE_URL` on the network (firewall, TLS, correct IP).

#### Comparison: split dev stack (Vite + API on another port)

**Defaults** in `cypress.config.ts` and **`.env.e2e.example`** target the **integrated** service at **`https://localhost:8443`** (same origin). For local development with Vite on **5173** and the API on **8080**, set in **`.env.e2e`**: `CYPRESS_BASE_URL=http://localhost:5173` and `CYPRESS_BACKEND_BASE_URL=http://localhost:8080` (dev-only axios behavior in `api.ts`). Do **not** mix 5173 + 8080 when testing the **production build** served with the API—use one origin for both.

### Setup (env file)

1. Copy the example env file:
   ```bash
   cp .env.e2e.example .env.e2e
   ```
2. Edit `.env.e2e` with the correct credentials/URLs for your environment (see **E2E against the real web service** when pointing at the integrated appliance).

### Run all E2E specs in order (Docker)

The Docker runner script runs specs in this order by default:
1. Join organization (Mailhog)
2. Offboard/onboard
3. Deployments wizard + details
4. Ensembles CRUD/JSON flows

```bash
./scripts/run-e2e-docker.sh
```

### Run from another machine

Set the base URLs to the reachable host/IP for the UI and backend:

```bash
CYPRESS_BASE_URL=http://appliance-host:5173 \\
CYPRESS_BACKEND_BASE_URL=http://appliance-host:8080 \\
./scripts/run-e2e-docker.sh
```

On Linux, you can also use host networking for the container:

```bash
DOCKER_NETWORK=host ./scripts/run-e2e-docker.sh
```

### Customize which specs run

Override the spec list (comma-separated) if you need a different order or a subset:

```bash
CYPRESS_SPECS=cypress/e2e/deployments.cy.ts,cypress/e2e/ensembles.cy.ts \\
./scripts/run-e2e-docker.sh
```

### Notes

- The join-organization spec uses Mailhog. Configure `CYPRESS_MAILHOG_BASE_URL`, `CYPRESS_MAIL_INBOX_DOMAIN`, and `CYPRESS_MAIL_SUBJECT_FRAGMENT` if you use a different setup.
- Override the join-org target with `CYPRESS_NUTEST_ORG_DID` and `CYPRESS_NUTEST_ROLE` if needed.
- For test-only orgs, place `known_organizations.e2e.json` next to the main known-orgs file on the appliance; it is merged at load time.
- The script uses `cypress/included:13.15.2` and installs dependencies inside the container. It keeps `node_modules` and pnpm store in Docker volumes so the repo stays clean.
