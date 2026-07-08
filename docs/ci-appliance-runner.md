# GitLab CI: appliance host + containerized live tests

Pipeline stages for live tests: **`test`** (unit only) → **`build`** → **`deploy`** (`appliance:prepare`) → **`e2e_test`**.

Live integration pytest, contract pytest, and Playwright E2E use **two runner types**:

| Runner tag | Executor | Role |
|------------|----------|------|
| **`appliance-dev-on`** | shell (on the appliance VM) | `appliance:prepare` (dev-on), `appliance:dev-off`, optional `appliance:package-smoke` |
| **`dedicated` + `docker`** | Docker | `pytest:integration+contract`, `playwright:e2e` (HTTP/browser against the appliance) |

Chromium and pytest run **inside containers** on the docker runner. The appliance stack runs in **dev-on** mode after `appliance:prepare` (repo `.venv` + `backend/` + CI-built `frontend/dist`). Set **`APPLIANCE_BASE_URL`** (GitLab CI variable or `.env.test`) to a URL **reachable from the docker runner** to the appliance HTTPS endpoint (not `localhost` from inside a container unless you use host networking locally).

All live-test jobs share **`resource_group: appliance-ci`** so only one pipeline uses the appliance at a time.

## Appliance host runner requirements

- Debian-based host with `nunet-appliance-web` (packaged base for dev-off fallback)
- GitLab Runner registered with tag `appliance-dev-on`, **shell** executor
- Passwordless **sudo** for the runner user (required by `nunet-web-mode.sh` and optional `ci-appliance-deploy.sh`)
- Gunicorn listening on `0.0.0.0:8443`; firewall allows inbound HTTPS from the docker runner network
- Host architecture must match **`build-packages:x86`** artifacts for `appliance:package-smoke` (typically `amd64`)

## CI variables (protected)

| Variable | Purpose |
|----------|---------|
| `APPLIANCE_ADMIN_PASSWORD` | Admin password for `POST /auth/token` |
| `APPLIANCE_BASE_URL` | HTTPS base URL of the appliance under test (must be reachable from docker runners) |
| `MAILHOG_USERNAME` / `MAILHOG_PASSWORD` | Mailhog basic auth for join-mail spec |
| `MAILHOG_BASE_URL` | Optional; default `https://mailhog.nunet.network` |

## Build artifacts

| Output | Source | Consumers |
|--------|--------|-----------|
| `frontend/dist/` | `build-frontend` (once per pipeline) | `build-packages:x86`, `build-packages:arm64`, `appliance:prepare` |
| `dist/*.deb` | `build-packages:x86` / `build-packages:arm64` | `deploy-packages`, `update-permalinks`, `appliance:package-smoke` |

`frontend/dist/` is passed via **GitLab job artifacts** (not cache) so docker build jobs and the appliance host reuse the same CI build without building twice.

## Job flow

```text
pytest:unit (test, container)

build-frontend (build, container) → frontend/dist artifact
        │
        ├── build-packages:x86 / build-packages:arm64 (ubuntu:24.04 + build.sh)
        │       └── deploy-packages / update-permalinks (main|release push only)
        │
        └── appliance:prepare (deploy, host) — dev-on + CI frontend/dist
                │
                ├── pytest:integration+contract (e2e_test, container)
                │
                └── playwright:e2e (e2e_test, container)
                │
        appliance:dev-off (e2e_test, host, when: always)
                │
        appliance:package-smoke (e2e_test, host, main|release push only) — optional .deb install
```

1. **`pytest:unit`** — `dedicated` + `docker`, `python:3.12.3-bookworm`; no live appliance.
2. **`build-frontend`** — `node:22-bookworm`; pnpm build once; artifact `frontend/dist/`.
3. **`build-packages:x86` / `build-packages:arm64`** — `ubuntu:24.04` container runs `build.sh` with `CI_SKIP_FRONTEND_BUILD=1`; publishes `dist/*.deb` artifacts.
4. **`appliance:prepare`** — `appliance-dev-on`: `ci-appliance-prepare.sh` runs dev-on with `DEV_MODE_SKIP_FRONTEND_BUILD=1` (reuses artifact `frontend/dist`), health check on `APPLIANCE_BASE_URL`. Can start via DAG as soon as `build-frontend` finishes (does not wait for deb builds).
5. **`pytest:integration+contract`** — Docker: `run-pytest.sh -m "integration or contract"`.
6. **`playwright:e2e`** — Docker Playwright image: `deploy/scripts/run-playwright-ci.sh` (native inside CI container; no Chromium on the appliance).
7. **`appliance:dev-off`** — `appliance-dev-on`: `nunet-web-mode.sh dev-off` (removes systemd override, restores packaged service).
8. **`appliance:package-smoke`** — optional on main/release push: installs CI `.deb`s via `ci-appliance-deploy.sh` after dev-off (does not gate e2e).

## Registering the appliance runner (example)

On the appliance VM:

```bash
# Install GitLab Runner per GitLab docs, then:
sudo gitlab-runner register \
  --url https://gitlab.com/ \
  --token <RUNNER_TOKEN> \
  --executor shell \
  --tag-list appliance-dev-on \
  --description "NuNet appliance CI host"
```

Ensure the runner user can run `sudo ./deploy/scripts/nunet-web-mode.sh` without a password prompt.

### Artifact download warnings on the host runner

When the shell executor downloads artifacts built in Docker jobs, GitLab Runner may log:

```text
WARNING: frontend/dist/: lchown ... operation not permitted
```

That happens because the runner cannot change ownership of files owned by another UID. The download still succeeds and dev-on can use `frontend/dist/`. Host jobs that only wait on upstream jobs (e.g. `appliance:dev-off`) should use `needs: ... artifacts: false` so test reports are not downloaded unnecessarily.

## Local parity

CI-equivalent dev-on + live tests (with prebuilt frontend):

```bash
# After build-frontend artifact or local: cd frontend && pnpm run build
set -a && source .env.test && set +a
export DEV_MODE_SKIP_FRONTEND_BUILD=1
./deploy/scripts/nunet-web-mode.sh dev-on

./deploy/scripts/run-pytest.sh -m "integration or contract"
./deploy/scripts/run-playwright-ci.sh
./deploy/scripts/nunet-web-mode.sh dev-off
```

Full local dev-on (builds frontend on host):

```bash
set -a && source .env.test && set +a
./deploy/scripts/nunet-web-mode.sh dev-on && ./deploy/scripts/nunet-web-mode.sh rebuild
./deploy/scripts/run-pytest.sh -m "integration or contract"
./deploy/scripts/run-playwright-ci.sh
./deploy/scripts/nunet-web-mode.sh dev-off
```

Optional packaged smoke (separate from e2e dev-on path):

```bash
./deploy/scripts/build.sh
sudo apt install -y dist/nunet-appliance-web_*_$(dpkg --print-architecture).deb
sudo systemctl restart nunet-appliance-web
curl -kSf https://localhost:8443/health
```

`run-playwright-ci.sh` defaults to Docker + the official Playwright image on the host. In GitLab `playwright:e2e`, it runs natively inside the Playwright CI image (`RUN_PLAYWRIGHT_NATIVE` behavior when `CI` is set).
