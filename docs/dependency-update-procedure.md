# Dependency Update Procedure

This runbook describes how to update frontend dependencies safely while keeping builds reproducible.

## Key Principle

- Normal builds are strict and reproducible.
- Dependency updates are explicit and intentional.

`devctl build` and GitLab CI use frozen lockfile installs, so dependency changes require a lockfile refresh before build.

## What Uses What

- Local package build path: `devctl build` -> `deploy/scripts/build.sh`
- CI package build path: `.gitlab-ci.yml` -> `deploy/scripts/build.sh`
- CI also runs `security:frontend-deps` before build jobs.

Both paths enforce:

- `pnpm install --frozen-lockfile`
- `pnpm audit --prod --audit-level=high` (strict mode by default)
- `pip-audit -r backend/nunet_api/requirements.txt --strict` in CI security stage

## When You Did Not Change Dependencies

No extra dependency steps are required.

Use your normal workflow:

1. `devctl build`
2. Push branch
3. CI runs security + build gates (Python and frontend dependency checks)

## When You Add or Update Dependencies

Run this process on your feature/update branch:

1. Update dependencies in `frontend/package.json`
   - prefer exact versions for direct dependencies
2. Regenerate lockfile intentionally
   - `cd frontend`
   - `corepack prepare pnpm@10.33.0 --activate`
   - `corepack pnpm install`
3. Validate locally
   - `corepack pnpm audit --prod --audit-level=high`
   - `corepack pnpm run build`
4. Commit dependency artifacts together
   - `frontend/package.json`
   - `frontend/pnpm-lock.yaml`
   - any policy updates (`frontend/.npmrc`, overrides, docs)
5. Run `devctl build` (should now pass frozen install checks)

### Python update helper script

Use `deploy/scripts/update_python_deps.sh` to automate Python dependency auditing and pin updates:

1. Audit only:
   - `deploy/scripts/update_python_deps.sh`
2. Auto-apply advisory-driven direct pin updates, then validate:
   - `deploy/scripts/update_python_deps.sh --apply-fixes`

The script updates only direct `name==version` entries in `backend/nunet_api/requirements.txt`, then runs install + strict `pip-audit` validation.

## Pull/Merge Request Checklist

- [ ] `frontend/package.json` and `frontend/pnpm-lock.yaml` are both committed
- [ ] `pnpm audit --prod --audit-level=high` passes
- [ ] `pip-audit -r backend/nunet_api/requirements.txt --strict` passes in CI
- [ ] `pnpm run build` passes
- [ ] no unreviewed dependency jumps
- [ ] changelog/release note checks done for critical packages

## Emergency Supply-Chain Response

If an upstream package is compromised or newly critical:

1. Pin direct dependency to known-safe version in `frontend/package.json`
2. Add `pnpm.overrides` for vulnerable transitive versions if needed
3. Regenerate and commit lockfile
4. Re-run audit/build
5. Merge and release

## Common Failure and Fix

Failure during `devctl build` or CI:

- `ERR_PNPM_OUTDATED_LOCKFILE`

Meaning:

- `package.json` changed but `pnpm-lock.yaml` was not refreshed.

Fix:

1. `cd frontend`
2. `corepack pnpm install`
3. Commit updated `pnpm-lock.yaml`

## Guardrails in This Repo

- Pinned package manager version via Corepack (`pnpm@10.33.0`)
- `minimumReleaseAge=1440` to avoid very fresh package publishes
- frozen lockfile installs in build and CI
- production audit gate in CI and build script
