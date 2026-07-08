"""OpenAPI contract tests (safe HTTP methods only) against a live appliance.

Disabled: Schemathesis runs are slow on a live appliance (many DMS subprocesses per
route) and do not give reliable signal yet. Re-enable by removing the skip below.
"""

from __future__ import annotations

import os

import httpx
import pytest

pytest.skip(
    "OpenAPI contract tests disabled (slow/unreliable against live DMS); use integration tests.",
    allow_module_level=True,
)
import schemathesis
from schemathesis.checks import not_a_server_error
from schemathesis.config import (
    CoveragePhaseConfig,
    ExamplesPhaseConfig,
    FuzzingPhaseConfig,
    GenerationConfig,
    PhasesConfig,
    ProjectConfig,
    ProjectsConfig,
    SchemathesisConfig,
    StatefulPhaseConfig,
)
from schemathesis.openapi import from_url

pytestmark = pytest.mark.contract

SAFE_METHODS = ("GET", "HEAD", "OPTIONS")
DEFAULT_BASE_URL = "https://localhost:8443"

# Smoke-style contract run: one generated case per operation, no fuzzing/coverage loops.
# Each DMS router GET fans out to several `nunet actor cmd` calls; extra Hypothesis
# phases multiplied that into hundreds of subprocess invocations on a live appliance.
_CONTRACT_CONFIG = SchemathesisConfig(
    projects=ProjectsConfig(
        default=ProjectConfig(
            tls_verify=False,
            phases=PhasesConfig(
                examples=ExamplesPhaseConfig(
                    enabled=True,
                    fill_missing=True,
                    generation=GenerationConfig(max_examples=1, no_shrink=True, deterministic=True),
                ),
                coverage=CoveragePhaseConfig(enabled=False),
                fuzzing=FuzzingPhaseConfig(enabled=False),
                stateful=StatefulPhaseConfig(enabled=False),
            ),
        ),
    ),
)


def _login_token(base: str, password: str) -> str:
    with httpx.Client(verify=False, timeout=60.0) as client:
        login = client.post(f"{base}/auth/token", json={"password": password})
        if login.status_code != 200:
            pytest.skip(f"Could not obtain JWT (status {login.status_code})")
        token = login.json().get("access_token")
        if not token:
            pytest.skip("Auth response missing access_token")
        return token


@pytest.fixture(scope="session")
def appliance_bearer_token() -> str:
    base = os.environ.get("APPLIANCE_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
    password = os.environ.get("APPLIANCE_ADMIN_PASSWORD", "").strip()
    if not password:
        pytest.skip("APPLIANCE_ADMIN_PASSWORD is not set")
    return _login_token(base, password)


@pytest.fixture(scope="session")
def openapi_schema(appliance_bearer_token):
    """Load schema at test time (not import time) so unit collection stays isolated."""
    base = os.environ.get("APPLIANCE_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
    return from_url(
        f"{base}/openapi.json",
        config=_CONTRACT_CONFIG,
        headers={"Authorization": f"Bearer {appliance_bearer_token}"},
        verify=False,
    )


schema = schemathesis.pytest.from_fixture("openapi_schema").include(method=list(SAFE_METHODS))


@schema.parametrize()
def test_api_contract(case, appliance_bearer_token):
    response = case.call(
        headers={"Authorization": f"Bearer {appliance_bearer_token}"},
        verify=False,
    )
    case.validate_response(response, checks=(not_a_server_error,))
