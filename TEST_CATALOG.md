# Test Catalog

This document provides an inventory of the implemented test suites and their current coverage across the NuNet platform, with a particular focus on the Appliance component.

The goal of this document is to provide a high-level view of what functionality is currently covered by automated tests and where each test belongs within the testing pyramid.

For details about the overall testing strategy, execution commands, DEV ON usage, and testing tiers, refer to the main README:

https://gitlab.com/nunet/appliance/-/blob/main/README.md#testing-dev-on-pyramid

## Notes

- This document is intended as a coverage inventory rather than detailed test documentation.
- Test implementations may contain multiple test cases and edge-case validations not explicitly listed here.
- No test coverage is included for Appliance process startup, service enablement, or environment provisioning/configuration.
- File names below represent the primary feature area covered by each test suite.

---

# Unit Tests

Unit tests focus on isolated behavior and use lightweight stubs or mocks where appropriate.

Path: `backend/tests/`

| Test Suite | Covered Area |
|---|---|
| `test_dms_resource_formatting.py` | DMS resource formatting behavior |
| `test_dms_resource_gpu_metadata.py` | GPU resource metadata handling |
| `test_nunet_api_api.py` | API utility behavior |
| `test_contract_enabled_flow.py` | Contract-enabled execution flow |
| `test_updater_scripts_env.py` | Updater environment configuration |
| `test_payments_env_config.py` | Payments environment settings |
| `test_payments_metadata_models.py` | Payments metadata models |
| `test_dms_manager_payment_quote_resilience.py` | Payment quote resilience handling |
| `test_update_version_comparison.py` | Version comparison logic |
| `test_environment_profile.py` | Environment profile behavior |
| `test_update_channels_env.py` | Update channel configuration |

---

# Integration Tests

Integration tests validate live API routers and interactions between application components.

Path: `backend/tests/integration`

| Test Suite | Covered Feature |
|---|---|
| `test_dms_status_router.py` | DMS status API endpoints |
| `test_organizations_router.py` | Organization management API |
| `test_ensemble_router.py` | Ensemble-related API behavior |
| `test_payments_router.py` | Payment API endpoints |
| `test_filesystem_router.py` | Filesystem API behavior |

---

# Contract API Tests

Contract tests validate API behavior against the OpenAPI schema and verify API contract consistency.

Path: `backend/tests/contract`

| Test Suite | Covered Feature |
|---|---|
| `test_openapi.py` | OpenAPI schema validation and contract checks |

---

# End-to-End (E2E) Tests

E2E tests validate complete user workflows through the browser using Playwright and DEV ON runtime behavior.

Path: `frontend/playwright`

| Test Suite | Covered User Workflow |
|---|---|
| `login-and-dashboard.spec.ts` | Login flow and dashboard access |
| `dms-offboard-onboard.spec.ts` | DMS onboarding and offboarding workflow |
| `dashboard-gpu-resources.spec.ts` | GPU resource visualization |
| `onboarding-mailhog.spec.ts` | Email onboarding flow |
| `onboarding-blockchain.spec.ts` | Blockchain onboarding workflow |
| `org-leave.spec.ts` | Organization leave flow |
| `ensembles.spec.ts` | Ensemble workflows |
| `deployments.spec.ts` | Deployment workflows |
| `payments-metadata.spec.ts` | Payment metadata behavior |
| `payments-quote-flow.spec.ts` | Payment quote workflow |
| `filesystem.spec.ts` | Filesystem workflow validation |

## E2E Support Files

Support files provide shared setup, helpers, and reusable utilities used by Playwright tests.

Path: `frontend/playwright`

| File | Purpose |
|---|---|
| `global-setup.ts` | Global Playwright initialization |
| `mailhog.ts` | MailHog integration utilities |
| `helpers.ts` | Shared E2E helper functions |
