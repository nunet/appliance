# Testing Architecture

The project has two completely separate test suites — backend (pytest) and frontend (Cypress) — with no shared runner and no CI automation.

---

## Backend Tests — pytest

**Location**: `backend/tests/` (11 files, ~3,000 LOC)

**Run with**:
```bash
./deploy/scripts/run-pytest.sh                    # all tests
./deploy/scripts/run-pytest.sh -v backend/tests/test_nunet_api_api.py
./deploy/scripts/run-pytest.sh backend/tests/test_nunet_api_api.py::test_health_endpoint
./deploy/scripts/run-pytest.sh -k "test_health"   # filter by name
```

The script auto-creates a `.venv`, sets `PYTHONPATH`, and installs `pytest`/`httpx` if missing — so it's self-contained.

**Test files:**

| File | What it tests |
|------|--------------|
| `test_nunet_api_api.py` | Full FastAPI endpoint suite (largest file) |
| `test_contract_enabled_flow.py` | Multi-step org contract workflow |
| `test_environment_profile.py` | Env config validation |
| `test_dms_manager_payment_quote_resilience.py` | DMS payment quote resilience |
| `test_dms_resource_formatting.py` | DMS resource formatting logic |
| `test_dms_resource_gpu_metadata.py` | DMS GPU metadata handling |
| `test_payments_env_config.py` | Payment environment config |
| `test_payments_metadata_models.py` | Payment metadata model validation |
| `test_update_channels_env.py` | Update channel env config |
| `test_update_version_comparison.py` | Version comparison logic |
| `test_updater_scripts_env.py` | Updater script env handling |

**Key patterns:**
- Session-scoped fixture stubs out heavy modules (`appliance_manager`, `dms_manager`, `org_manager`, etc.) by injecting into `sys.modules`
- Tests use FastAPI's `TestClient` with Bearer token auth (password: `TestFixturePwd9!`)
- `raw_client` fixture available for testing unauthenticated flows
- Fixture hierarchy: session-scoped stubs → app fixture → per-test clients

---

## Frontend Tests — Cypress E2E

**Location**: `frontend/cypress/e2e/` (11 specs, ~2,600 LOC)

**Run with**:
```bash
cd frontend
cp .env.e2e.example .env.e2e   # configure once
pnpm cy:open                    # interactive (recommended for development)
pnpm cy:run                     # headless
./scripts/run-e2e-docker.sh     # Docker-isolated (CI-equivalent)
```

**Test specs:**

| Spec | What it tests |
|------|--------------|
| `join-org-blockchain.cy.ts` | MetaMask/Web3 org join flow |
| `join-org-mailhog.cy.ts` | Email-based org join (Mailhog) |
| `offboard-onboard.cy.ts` | Device onboarding/offboarding lifecycle |
| `deployments.cy.ts` | Deployment create/configure/deploy |
| `ensembles.cy.ts` | Ensemble CRUD + YAML editing |
| `payments-quote-flow.cy.ts` | Payment quote + DMS peer negotiation |
| `payments-metadata.cy.ts` | Payment metadata model handling |
| `org-leave.cy.ts` | Leave organization flow |
| `filesystem.cy.ts` | File system operations |
| `dashboard-gpu-resources.cy.ts` | GPU resource dashboard updates |
| `real-appliance-dashboard.cy.ts` | Live appliance integration |

**Key patterns:**
- All API calls interceptable with `cy.intercept()` for mock control
- Auth is JWT stored in `localStorage`, managed via `cy.loginOrInitialize()` custom command
- `.env.e2e` controls base URLs, credentials, Mailhog settings, and timeouts
- `ENSEMBLE_SKIP_DESTRUCTIVE=true` flag protects against teardown on real hardware

**Custom commands** (`cypress/support/e2e.ts`):

| Command | Purpose |
|---------|---------|
| `cy.loginOrInitialize()` | Handles first-run setup and subsequent logins |
| `cy.resetOnboarding()` | Resets appliance state via API before tests |
| `cy.waitForMail()` | Polls Mailhog for email arrival (configurable timeout) |
| `cy.ensureAppMode('simple'\|'advanced')` | Sets UI mode |
| `cy.cleanupEnsembleByStem()` | Test teardown helper |
| `cy.logStep()` | Log test step with prefix |

---

## Configuration

**Cypress** (`frontend/cypress.config.ts`):
- Default base URL: `https://localhost:8443` (integrated appliance)
- Dev split mode: UI on `:5173`, API on `:8080`
- 3 retries in headless mode, `experimentalMemoryManagement: true`

**Backend**: No `pytest.ini` — pytest defaults apply. All configuration is handled by `run-pytest.sh`.

### Integrated service control (`nunet-web-mode.sh`)

When validating against the real web service, use:

```bash
./deploy/scripts/nunet-web-mode.sh dev-on
./deploy/scripts/nunet-web-mode.sh rebuild
./deploy/scripts/nunet-web-mode.sh status
./deploy/scripts/nunet-web-mode.sh dev-off
```

- `dev-on` writes a systemd drop-in so `nunet-appliance-web` runs from repo backend (`.venv`) and repo frontend build (`frontend/dist`).
- `rebuild` refreshes venv + frontend build and restarts the unit.
- `status` prints active unit wiring (`DropInPaths`, `ExecStart`, `Environment`) to confirm you are testing the expected target.
- `dev-off` removes the override and returns to packaged defaults.

---

## Backend vs Frontend Comparison

| Aspect | Backend | Frontend |
|--------|---------|----------|
| Framework | pytest | Cypress 13.15.2 |
| Language | Python | TypeScript |
| Test types | Unit, integration, flow | E2E workflow |
| Auth pattern | Bearer token (header) | JWT in localStorage |
| Mocking | `sys.modules` injection + TestClient | `cy.intercept()` + localStorage |
| Coverage | Not configured | Not configured |
| CI integration | Manual only | Manual only |

---

## Development Workflow

**Backend — while iterating:**
```bash
./deploy/scripts/run-pytest.sh -q                    # quick full run
./deploy/scripts/run-pytest.sh -k "test_name"        # run matching tests
```

**Frontend — while iterating:**
```bash
cd frontend
pnpm cy:open   # leave open; re-run specs interactively as you edit
```
Point at your dev server by setting `CYPRESS_BASE_URL` in `.env.e2e`.

**Before merging (no CI gate — must be run manually):**
```bash
./deploy/scripts/run-pytest.sh
cd frontend && pnpm cy:run    # or ./scripts/run-e2e-docker.sh for full isolation
```

---

## Known Gaps

- **No CI test execution** — tests won't catch regressions unless run manually before merge
- **No code coverage** — neither pytest-cov nor Cypress coverage plugins are configured
- **No frontend unit tests** — only E2E; component-level bugs require a running app to surface
- **Cypress requires setup** — not runnable from a cold checkout without configuring `.env.e2e` and a live (or mocked) appliance
