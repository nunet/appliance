# Testing Setup Proposal

**Status:** Proposal — under review
**Relates to:** `docs/testing-architecture.md` (current state)

---

## Problem Statement

The current test suite has a fundamental reliability gap: tests can pass while the application is broken for real users. This happens for two reasons:

1. **Backend tests do not currently provide live-server contract coverage.** The suite has 11 pytest files, but only a subset uses FastAPI `TestClient` and heavy module stubbing (primarily `test_nunet_api_api.py`, plus targeted `TestClient` coverage in `test_payments_metadata_models.py`). Passing still says little about whether DMS integration, filesystem behavior, or auth lifecycle work on a real running appliance.

2. **Cypress E2E is sometimes mis-targeted.** The `cypress.config.ts` correctly defaults to `https://localhost:8443` (the production stack), but developer documentation and tooling also offer the split dev stack (`:5173` + `:8080`) as an E2E target. These are not equivalent — the production frontend uses **relative API paths**, meaning the split dev stack tests a fundamentally different network topology than what users experience.

Secondary gaps: no CI test automation, no code coverage, no clear separation between "tests that require a live appliance" and "tests that run anywhere".

---

## Guiding Principles

**1. The test environment must match production.**
Tests that pass in an environment users never experience are not E2E tests. The only valid target for Cypress is the production stack on `https://localhost:8443`.

**2. Fast feedback and real confidence serve different purposes — both are needed.**
Mocked tests give fast feedback during development. Live tests give confidence before shipping. Neither replaces the other.

**3. Tests should be deterministic and ordered by trust.**
A clear test pyramid with explicit gates avoids the failure mode of "mocked tests passed but prod is broken."

**4. Maintainability means low friction to add and run tests.**
If running tests requires complex setup, developers skip them. Every layer needs a single command.

---

## Validation Against Current Repo (Mar 2026)

The core direction is strong and aligns with current repository behavior. The most important principle (live testing against integrated `https://localhost:8443`) is already consistent with current Cypress defaults and project docs/rules.

### Confirmed

- `frontend/cypress.config.ts` defaults both base URLs to `https://localhost:8443`.
- `frontend/src/api/api.ts` uses same-origin relative API paths in production mode.
- `deploy/scripts/nunet-web-mode.sh rebuild` exists and is already wired into Cypress via `CYPRESS_REBUILD_FRONTEND=true`.
- Current CI (`.gitlab-ci.yml`) builds/packages only; no pytest/Cypress jobs currently run.

### Clarifications to keep this proposal accurate

- **`run-live-tests.sh` is proposed, not present yet.**
  - The proposal references `./deploy/scripts/run-live-tests.sh`, but that script does not currently exist.
  - Treat it as a planned deliverable in this proposal.

- **`nunet-web-mode.sh` now implements full toggle flow (`dev-on`/`dev-off`/`rebuild`/`status`).**
  - `dev-on` writes a systemd drop-in override to run the web service from repo backend/frontend paths.
  - `dev-off` removes the override and restores packaged defaults.
  - `status` exposes active `DropInPaths`, `ExecStart`, and environment for verification.

- **Layer 3 test ordering is only partially enforced today.**
  - `frontend/scripts/run-e2e-docker.sh` defines an explicit ordered spec list.
  - `pnpm cy:run` does not inherently guarantee the same integration-pipeline order.
  - Recommendation: codify Layer 3 ordering in a single canonical runner to avoid drift.

---

## The Critical Environment Decision

### Why split dev (`http://localhost:8080`) is wrong for E2E

The production `api.ts` uses **relative paths** (e.g. `/dms/status`, `/auth/token`). These are resolved against whatever origin serves the frontend — which in production is `https://localhost:8443`. When you test against the split dev stack, the Vite proxy or CORS bridging creates a cross-origin setup that does not exist in production. You are testing a configuration that no user ever sees.

Specifically, split dev bypasses:
- TLS and certificate handling
- Any routing or header behaviour from the production server
- Static file serving via FastAPI (Vite serves unbundled modules instead of the built bundle)
- The same-origin API call pattern that production uses

### The production stack as the canonical test target

The production service (`nunet-appliance-web.service`) runs the full stack:
- Gunicorn/Uvicorn on `PORT=8443`, serving the React SPA and the API from the same process
- TLS configured directly on the server
- `NUNET_STATIC_DIR` pointing at the built frontend bundle
- All system integrations (DMS, Docker, filesystem) active

**`https://localhost:8443` is the single canonical URL for all live testing** — both backend pytest and Cypress E2E.

### The dev-on switch

A **systemd drop-in** for `nunet-appliance-web` can point the live service at the git checkout instead of the installed PEX and packaged static assets. When active (`dev-on`), the service continues to run on port 8443 with full TLS and all system integrations, but:
- Python backend resolves from the repo's `.venv` and `backend/` source (with `--reload`)
- `NUNET_STATIC_DIR` points at the repo's `frontend/dist`

This is the correct mode for all live testing. It means backend source changes and frontend source changes are both testable against the real service — no PEX rebuild required, no split-origin workaround needed.

`dev-off` restores the packaged paths by removing the override and restarting the service.

### Rebuilding the frontend for testing

`./deploy/scripts/nunet-web-mode.sh rebuild` builds the SPA from the current source and restarts the service:

```bash
./deploy/scripts/nunet-web-mode.sh rebuild   # build frontend/dist + restart service
./deploy/scripts/nunet-web-mode.sh status    # check service state
```

Cypress can trigger this automatically before a run by setting `CYPRESS_REBUILD_FRONTEND=true` in `.env.e2e`. This is the recommended approach for full-stack test runs: one flag ensures the service is serving the current source before any spec executes.

### Where split dev remains valid

| Task | Right environment |
|------|------------------|
| Active frontend development (HMR) | Split dev (`devctl dev up`) |
| Active backend development (hot reload) | Split dev (`devctl dev up`) |
| Mocked pytest (fast unit feedback) | TestClient — no server at all |
| Backend live API contract tests | `https://localhost:8443` with dev-on |
| Cypress E2E | `https://localhost:8443` with dev-on |

The cursor rules are explicit: *"prefer `nunet-web-mode` when validating behaviour through the real `nunet-appliance-web` service."* Split dev (`devctl dev up`) is a lighter loop for iteration; it is not a test environment.

---

## Proposed Test Layers

### Layer 1 — Mocked Unit / Integration (pytest)

**What it tests:** API routing logic, response schemas, data parsing, environment config, auth flow mechanics — against a fully stubbed in-process server.

**When to run:** On every backend file save during development. Always before committing.

**Target:** FastAPI `TestClient` — no running server required.

**Command:**
```bash
./deploy/scripts/run-pytest.sh          # all mocked tests
./deploy/scripts/run-pytest.sh -q       # quiet, just pass/fail
./deploy/scripts/run-pytest.sh -k auth  # filter by name
```

**Current state:** Good. 11 files, ~3,000 LOC. Keep as-is.

**Confidence level:** API logic is correct. Says nothing about real integrations.

---

### Layer 2 — Backend Live API Contract Tests (pytest + httpx)

**What it tests:** The running backend server, with no mocking. Validates that auth enforcement is correct, all route groups return well-formed responses, and the authentication lifecycle (login → token → refresh) works end-to-end.

**When to run:** Before committing backend changes. After any router or middleware change.

**Target:** `https://localhost:8443` — the production service with `dev-on` active (repo source, repo venv, `frontend/dist` from the repo). The service must be running.

**Command:**
```bash
# dev-on must be active (systemd drop-in pointing service at the repo)
# Service runs on https://localhost:8443 from repo source

export PYTEST_ADMIN_PASSWORD=yourpassword
./deploy/scripts/run-live-tests.sh
```

**Fixture design:**
- `conftest.py` adds `--live-url` pytest CLI option (also reads `PYTEST_LIVE_URL` env var)
- `api_client` fixture: unauthenticated `httpx.Client`; auto-skips if no URL provided
- `authed_api_client` fixture: logs in once per session, yields Bearer-token client
- Existing mocked tests are unaffected (different fixtures, different file)

**Test classes:**

| Class | Routes | Notes |
|-------|--------|-------|
| `TestHealth` | `GET /health` | Server reachability |
| `TestAuthEnforcement` | All 8 protected route prefixes | Expects 401 without token |
| `TestAuthFlow` | `/auth/status`, `/auth/token`, `/auth/refresh` | Full login lifecycle |
| `TestSystemInfo` | `/sys/environment`, `/sys/appliance-version` | Schema validation |
| `TestDMS` | `/dms/status`, `/dms/status/full` | Valid response shape regardless of DMS state |
| `TestOrganizations` | `/organizations/known`, `/organizations/joined` | List types |
| `TestEnsemble` | `/ensemble/templates`, `/ensemble/deployments` | List types |
| `TestFilesystem` | `/filesystem/list` | 200 or 403 (allowlist) — server responded |
| `TestPayments` | `/payments/list_payments`, `/payments/config` | 200 or 502 (DMS down) |

**Confidence level:** Backend API contract is correct and auth is enforced. Does not test UI, does not test the TLS/proxy stack.

---

### Layer 3 — Cypress E2E: Real User Flows

**What it tests:** Complete user-facing workflows, from browser through TLS through API through system integrations. No intercepts, no mocks.

**When to run:** Before merging. Before a release. Any time a full-stack change is made.

**Target:** `https://localhost:8443` — the production service, with `NUNET_STATIC_DIR` overridden to point at the repo's built frontend. Both `CYPRESS_BASE_URL` and `CYPRESS_BACKEND_BASE_URL` must be set to the same value (same-origin requirement).

**Workflow:**
```bash
# 1. Build frontend from current source
cd frontend && pnpm run build && cd ..

# 2. Point production service at the new build
#    Edit /etc/nunet-appliance-web/app.env:
#    NUNET_STATIC_DIR=/home/ubuntu/repo/appliance/frontend/dist
sudo systemctl restart nunet-appliance-web

# 3. Configure Cypress
cp frontend/.env.e2e.example frontend/.env.e2e
# Set: CYPRESS_BASE_URL=https://localhost:8443
#      CYPRESS_BACKEND_BASE_URL=https://localhost:8443
#      CYPRESS_ADMIN_PASSWORD=yourpassword
#      CYPRESS_VERIFY_SSL=false

# 4. Run
./deploy/scripts/run-live-tests.sh --with-cypress
# Or Cypress directly:
cd frontend && pnpm cy:run
```

**Current real specs (7 of 11):**

| Spec | User journey tested |
|------|-------------------|
| `join-org-mailhog.cy.ts` | Full org join via email verification |
| `offboard-onboard.cy.ts` | DMS onboard/offboard lifecycle |
| `deployments.cy.ts` | Deployment wizard → peer selection → deploy |
| `ensembles.cy.ts` | Ensemble CRUD (YAML and JSON) |
| `org-leave.cy.ts` | Leave organisation flow |
| `filesystem.cy.ts` | File CRUD (create, upload, rename, copy, move, delete) |
| `real-appliance-dashboard.cy.ts` | Login + dashboard readiness |

These run in order. The sequence is intentional: join org → use resources → leave org.

**Confidence level:** The highest. Passing means the real user workflow works on this hardware, with this software, under production conditions.

---

### Layer 4 — Cypress UI Isolation Tests (intercepts)

**What it tests:** UI rendering, state machine logic, and edge cases that cannot be tested live because they require specific backend states that are hard or impossible to reproduce (no MetaMask, no on-chain payment state, specific GPU hardware, specific DMS error conditions).

**These are not E2E tests.** They are browser-based integration tests that validate UI behaviour in isolation.

**Current 4 specs:**

| Spec | What it actually tests |
|------|----------------------|
| `join-org-blockchain.cy.ts` | Blockchain wallet selector UI, form validation, request payload shape |
| `payments-quote-flow.cy.ts` | Quote state machine: creation, expiry, retry, stored-quote resume |
| `dashboard-gpu-resources.cy.ts` | GPU resource rendering from `onboarded_resources` field |
| `payments-metadata.cy.ts` | Metadata rendering, sad paths, disabled states |

**When to run:** Any time a UI change touches these flows. Can run without a live backend.

**Target:** Any URL — these specs mock all API responses via `cy.intercept()`.

**Proposed classification change:** These specs should be clearly distinguished from Layer 3. Options (in order of preference):

1. **Move to `cypress/ui/` directory.** Clearest separation. Requires updating `cypress.config.ts` spec pattern.
2. **Keep in `cypress/e2e/` but rename with a `.ui.cy.ts` suffix.** Low friction. Naming makes the distinction visible.
3. **Document the distinction without moving files.** Least friction. Risk: the distinction erodes over time.

Recommendation: Option 1 (move to `cypress/ui/`). The directory name communicates intent to every new contributor without reading documentation.

---

## Proposed Directory Structure

```
backend/
  tests/
    conftest.py                          # NEW: live test fixtures + --live-url flag
    test_live_integration.py             # NEW: Layer 2 tests (real HTTP)
    test_nunet_api_api.py                # existing: Layer 1 (mocked)
    test_contract_enabled_flow.py        # existing
    test_environment_profile.py          # existing
    test_dms_*.py                        # existing
    test_payments_*.py                   # existing
    test_update_*.py                     # existing

frontend/
  cypress/
    e2e/                                 # Layer 3: real E2E (require live 8443)
      real-appliance-dashboard.cy.ts
      join-org-mailhog.cy.ts
      offboard-onboard.cy.ts
      deployments.cy.ts
      ensembles.cy.ts
      org-leave.cy.ts
      filesystem.cy.ts
    ui/                                  # NEW: Layer 4: UI isolation (intercepts)
      join-org-blockchain.cy.ts
      payments-quote-flow.cy.ts
      dashboard-gpu-resources.cy.ts
      payments-metadata.cy.ts
    support/
      e2e.ts

deploy/
  scripts/
    run-pytest.sh                        # existing: Layer 1
    run-live-tests.sh                    # NEW: Layer 2 + optional Layer 3
```

---

## CI/CD Integration

Currently no tests run in CI. The GitLab pipeline only builds DEB packages.

### Proposed stages

**Stage: `test` (on every MR, every push to `main`)**

Add a `test:backend` job to `.gitlab-ci.yml`:
```yaml
test:backend:
  stage: test
  script:
    - ./deploy/scripts/run-pytest.sh -q
  rules:
    - if: '$CI_PIPELINE_SOURCE == "merge_request_event"'
    - if: '$CI_COMMIT_BRANCH == "main"'
```

Requirements: just Python. No services, no hardware. Runs in < 60 seconds.

This is the highest-value CI addition: it catches backend regressions on every MR with minimal infrastructure cost.

**ESLint (on every MR):**
```yaml
test:lint:
  stage: test
  script:
    - cd frontend && pnpm install --frozen-lockfile && pnpm run lint
```

**Live integration + Cypress (on a self-hosted runner with a real appliance):**

These cannot run in a standard GitLab CI runner — they require real hardware with DMS, systemd, and network access. If a dedicated test appliance is available as a GitLab runner:

```yaml
test:e2e:
  stage: test
  tags: [appliance]          # targets the self-hosted runner
  script:
    - pnpm run build
    - export PYTEST_ADMIN_PASSWORD=$APPLIANCE_TEST_PASSWORD
    - ./deploy/scripts/run-live-tests.sh --with-cypress
  rules:
    - if: '$CI_COMMIT_BRANCH == "main"'
    - when: manual
```

This is aspirational — it requires a persistent test appliance and a GitLab runner registration. It is the right long-term goal.

### Near-term CI gate (practical minimum)

Without a self-hosted appliance runner, the practical minimum CI gate is:
1. `test:backend` (mocked pytest) — automated on every MR
2. `test:lint` (ESLint) — automated on every MR
3. **Developer responsibility**: run `run-live-tests.sh --with-cypress` locally before merging anything that touches API contracts or user-facing flows

The developer responsibility is a process gap, not a technical one. It should be documented explicitly in `CONTRIBUTING.md` as a required pre-merge step.

---

## Developer Workflows

### During backend development

```bash
# Fast feedback loop (mocked, no server needed):
./deploy/scripts/run-pytest.sh -q            # ~3 seconds, run constantly

# Before committing (requires dev-on active):
export PYTEST_ADMIN_PASSWORD=yourpassword
./deploy/scripts/run-live-tests.sh           # Layer 2: real API contract against https://localhost:8443
```

### During frontend development

```bash
# Fast iteration (HMR, split dev — not a test environment):
./deploy/scripts/devctl.sh dev up
# Edit React source; see changes instantly at http://localhost:5173

# Before committing (test against the real service):
./deploy/scripts/nunet-web-mode.sh rebuild   # build + restart service on https://localhost:8443
cd frontend && pnpm cy:open                  # run specs interactively against https://localhost:8443
```

### Before merging any change

```bash
# 1. Mocked tests (always, no server needed)
./deploy/scripts/run-pytest.sh -q

# 2. Ensure dev-on is active and frontend is built
./deploy/scripts/nunet-web-mode.sh rebuild   # builds frontend/dist, restarts service

# 3. Full live test run
export PYTEST_ADMIN_PASSWORD=yourpassword
./deploy/scripts/run-live-tests.sh --with-cypress
# (Cypress can also auto-rebuild: set CYPRESS_REBUILD_FRONTEND=true in .env.e2e)
```

---

## Test State and Ordering

The Layer 3 Cypress suite has ordering dependencies that are intentional and should be made explicit:

```
join-org-mailhog       → appliance must be onboarded but not yet joined
offboard-onboard       → appliance must be joined (set up by previous test)
deployments            → appliance must be joined and DMS running with peers
ensembles              → no state dependency (CRUD only)
org-leave              → appliance must be joined (cleanup of earlier state)
```

This means Layer 3 tests are not independently re-runnable in arbitrary order — they form an **integration pipeline**. This is a valid design for appliance-level testing (you can't deploy without joining first), but it must be documented.

**Implications:**
- A test appliance for CI must be returned to a known pre-join state before each full run
- The `cy.resetOnboarding()` custom command handles per-spec state cleanup within a run, but does not handle the between-run state
- For local development, developers may run individual specs against an already-joined appliance (most specs work fine in isolation)

---

## Gaps Not Addressed in This Proposal

The following are out of scope for the immediate implementation but should be tracked:

**Frontend component unit tests (Vitest)**
Currently there are no unit tests for React components. The 4 UI isolation Cypress specs partially fill this role but are slow and browser-dependent. Vitest with Testing Library would give fast (< 1s) component-level feedback. This is a non-trivial investment and should be a separate initiative.

**Code coverage**
Neither backend nor frontend has coverage configured. Adding `pytest-cov` to the mocked test run is low-effort and high-value for identifying untested code paths. Cypress coverage requires instrumentation of the built bundle and is more complex.

**Backend type enforcement**
The backend has partial type hints. Mypy or Pyright in CI would catch type errors before runtime.

---

## Summary

| Layer | Type | Target | When | Confidence |
|-------|------|--------|------|-----------|
| 1 — Mocked pytest | Unit/integration | TestClient (in-process) | Every save, every commit | API logic correct |
| 2 — Live pytest | API contract | `https://localhost:8443` (dev-on) | Before committing backend changes | API works on real service |
| 3 — Cypress E2E | Full stack | `https://localhost:8443` (dev-on) | Before merging, before release | Users can use the product |
| 4 — Cypress UI | UI isolation | Any (intercepts only) | Before merging UI changes | UI renders edge cases correctly |

**The single most important principle:** All live testing — both pytest and Cypress — targets `https://localhost:8443` with `dev-on` active. This is the real service running from repo source. Split dev (`devctl dev up`) is a development convenience, not a test environment.

---

## Review Notes

_Reviewer pass — verified against the appliance repo on 2026-03-26._

### Core Principles: Solid

The four guiding principles are correct and well-grounded in how this codebase actually works:

1. **"Test environment must match production"** — Verified. `frontend/src/api/api.ts` returns `""` (empty string) for `baseURL` in production mode, making all API calls relative to the serving origin. Testing against `:5173`/`:8080` split dev creates a fundamentally different network path that no user ever hits. This is not a theoretical concern — it's how the code works.

2. **"Fast feedback and real confidence serve different purposes"** — The existing mocked pytest suite (~3,000 LOC, 11 files) is a solid Layer 1. The proposal correctly identifies that passing mocked tests says nothing about DMS, filesystem, or auth on real hardware.

3. **"Deterministic and ordered by trust"** — The four-layer pyramid is a sound architecture. The ordering dependencies in Layer 3 (join → use → leave) are honest about the constraints of appliance-level testing.

4. **"Low friction to add and run tests"** — `run-pytest.sh` already achieves this for Layer 1 (auto-creates venv, auto-installs deps). The proposal extends this pattern to `run-live-tests.sh`.

### Verified Against the Repo

| Claim | Status | Evidence |
|-------|--------|----------|
| Backend tests are predominantly mocked, with heavy stubbing concentrated in specific files | **Partially confirmed** | `test_nunet_api_api.py` has session-level `sys.modules` stubs; `TestClient` appears in 2 files; live HTTP coverage is not present |
| Production `api.ts` uses relative paths | **Confirmed** | `getBaseURL()` returns `""` in production; `baseURL: getBaseURL()` on axios instance |
| `cypress.config.ts` defaults to `https://localhost:8443` | **Confirmed** | Line 185: `process.env.CYPRESS_BASE_URL ?? "https://localhost:8443"` |
| No CI test automation exists | **Confirmed** | `.gitlab-ci.yml` has only version/build/deploy stages |
| 11 Cypress specs, 11 pytest files | **Confirmed** | Exact match |
| `nunet-web-mode.sh rebuild` works as described | **Confirmed** | Script does `pnpm install`, `pnpm build`, `systemctl restart` |
| `CYPRESS_REBUILD_FRONTEND` integration exists | **Confirmed** | `cypress.config.ts` `before:run` hook calls `nunet-web-mode.sh rebuild` |
| No Vitest/Jest/Playwright in project | **Confirmed** | Not in `package.json` devDependencies |
| `cy.resetOnboarding()` custom command exists | **Confirmed** | `cypress/support/e2e.ts` — POSTs to `/organizations/onboarding/reset` |
| Cursor rules align with proposal | **Confirmed** | `.cursor/rules/testing.mdc` documents the same split-dev vs integrated distinction |

### The 7/4 Spec Classification — Nuanced but Correct

The proposal classifies 7 specs as "real E2E" and 4 as "UI isolation." Intercept counts from the repo:

| Spec | `cy.intercept` calls | Proposal classification |
|------|-----------------------|------------------------|
| `join-org-mailhog.cy.ts` | 0 | Layer 3 (real E2E) ✓ |
| `offboard-onboard.cy.ts` | 0 | Layer 3 (real E2E) ✓ |
| `ensembles.cy.ts` | 0 | Layer 3 (real E2E) ✓ |
| `org-leave.cy.ts` | 0 | Layer 3 (real E2E) ✓ |
| `real-appliance-dashboard.cy.ts` | 1 | Layer 3 (real E2E) ✓ |
| `deployments.cy.ts` | 4 | Layer 3 (real E2E) — see note |
| `filesystem.cy.ts` | 6 | Layer 3 (real E2E) — see note |
| `payments-quote-flow.cy.ts` | 23 | Layer 4 (UI isolation) ✓ |
| `payments-metadata.cy.ts` | 15 | Layer 4 (UI isolation) ✓ |
| `dashboard-gpu-resources.cy.ts` | 14 | Layer 4 (UI isolation) ✓ |
| `join-org-blockchain.cy.ts` | 5 | Layer 4 (UI isolation) ✓ |

**Note:** `deployments.cy.ts` and `filesystem.cy.ts` use a handful of intercepts despite being classified as real E2E. This is likely for targeted purposes (wait aliases, specific edge cases) rather than full API mocking. The classification is still reasonable — the intent is real-service testing — but the proposal could acknowledge that some Layer 3 specs use limited intercepts for test mechanics without invalidating their E2E nature.

### Items That Don't Exist Yet (Clarity Suggestion)

The proposal references several artifacts as though they're part of the workflow, but they are **proposed, not yet implemented**:

- **`run-live-tests.sh`** — does not exist under `deploy/scripts/`. The directory structure section marks it as "NEW" which is correct, but the Developer Workflows section (lines 346-347, 370-373) reads as executable instructions. Consider adding a note that these workflows depend on implementing the script first, or adding a simple "Implementation Checklist" section.
- **`backend/tests/conftest.py`** — does not exist. The Layer 2 fixture design (`--live-url`, `api_client`, `authed_api_client`) is well-designed but needs to be built.
- **`backend/tests/test_live_integration.py`** — does not exist. The test class table (Layer 2) is a good contract but needs implementation.

This is fine for a proposal, but the document would benefit from a clear "what exists today" vs "what needs to be built" delineation, especially since some developer workflow commands reference both existing and proposed scripts.

### `dev-on` / `dev-off` — now implemented

`deploy/scripts/nunet-web-mode.sh` now provides the full toggle implementation:

- `dev-on`: prepares venv, builds frontend, writes systemd override, restarts service.
- `dev-off`: removes override and restarts service to packaged defaults.
- `rebuild`: refreshes venv/frontend and restarts.
- `status`: prints current unit wiring (including drop-ins and `ExecStart`).

### CI Proposal: Pragmatic and Correct

The near-term CI gate (mocked pytest + ESLint on every MR) is the right first move. It requires zero infrastructure beyond what GitLab CI already provides and catches the highest-value regressions. The self-hosted runner for live tests is correctly flagged as aspirational.

One addition worth considering: the `test:backend` job should pin the Python version to match what the appliance runs in production (the README says Python 3.10+). The `ubuntu:24.04` image used by build jobs ships Python 3.12 — fine for mocked tests, but worth being explicit about.

### Minor Suggestions for Future Iterations

1. **Layer 4 directory move** — The recommendation to move UI isolation specs to `cypress/ui/` is sound. Note that `cypress.config.ts` currently has `specPattern: "cypress/e2e/**/*.cy.ts"` — it would need a second pattern or a glob update to also pick up `cypress/ui/` specs.

2. **`pytest-cov`** — Mentioned in "Gaps Not Addressed" as low-effort. Agreed. Could be added to `run-pytest.sh` with a `--cov` flag without changing anything else.

3. **Test ordering documentation** — The test state/ordering section is excellent. Consider encoding the ordering as a comment block at the top of a Cypress config or a dedicated `SPEC_ORDER.md` so it lives with the specs, not just in this proposal.

### Bottom Line

The core principles are solid and directly verified by the codebase. The four-layer model accurately reflects the testing reality of an appliance that depends on real hardware, systemd, DMS, and same-origin API routing. The proposal correctly identifies that the split dev stack is not a valid E2E target — this is the single most important insight and it's backed by how `api.ts` actually resolves URLs in production. Ship it, iterate from there.
