# Dependency Security and Lockfile Policy

This project uses `pnpm` with a committed lockfile to keep installs reproducible and reduce supply-chain risk.

For the operational runbook used by developers, see [`docs/dependency-update-procedure.md`](dependency-update-procedure.md).

## Baseline Rules

- Keep `frontend/pnpm-lock.yaml` committed and in sync with `frontend/package.json`.
- Use frozen installs for normal workflows:
  - CI: `pnpm install --frozen-lockfile`
  - Build scripts: `pnpm install --frozen-lockfile`
- Pin package manager version with Corepack (`pnpm@10.33.0`).

## CI Security Gates

The CI pipeline includes dedicated dependency audit jobs:

1. `security:python-deps`
   - installs `pip-audit`
   - runs `pip-audit -r backend/nunet_api/requirements.txt --strict`
2. `security:frontend-deps`
   - activates the pinned pnpm version through Corepack
   - installs with `--frozen-lockfile`
   - runs `pnpm audit --prod --audit-level=high`

If vulnerabilities are detected, the pipeline fails before package build/deploy jobs.

The package build script also enforces the same audit check by default (`STRICT_PNPM_AUDIT=1`).

## Safe Dependency Update Workflow

Use this workflow when intentionally updating dependencies:

1. Create a dedicated update branch.
2. Update dependency specifiers in `frontend/package.json` as needed.
3. Regenerate lockfile:
   - `corepack prepare pnpm@10.33.0 --activate`
   - `corepack pnpm install`
4. Verify:
   - `corepack pnpm audit --prod --audit-level=high`
   - `corepack pnpm run build`
5. Commit both `frontend/package.json` and `frontend/pnpm-lock.yaml` together.

Do not regenerate lockfiles in deployment hotfixes unless the dependency change is intentional and reviewed.

For Python dependency automation, use `deploy/scripts/update_python_deps.sh` (audit-only or `--apply-fixes` mode).

## Emergency Response Pattern

If a supply-chain incident is reported:

1. Pin the affected package to a known-safe version in `frontend/package.json`.
2. Add or adjust `pnpm.overrides` for vulnerable transitive packages.
3. Regenerate and commit lockfile.
4. Re-run audit/build gates before merge.

## Local Policy Settings

`frontend/.npmrc` contains project-level safety defaults:

- `minimumReleaseAge=1440`
- `trustPolicy=no-downgrade`
- `save-exact=true`
- `prefer-frozen-lockfile=true`
- `verify-store-integrity=true`
- `engine-strict=true`

These settings are guardrails. CI checks and code review remain the enforcement layer.
