"""Shared pytest hooks and fixtures for backend/tests."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import httpx
import pytest

DEFAULT_BASE_URL = "https://localhost:8443"


@pytest.fixture(scope="session", autouse=True)
def _stub_caddy_proxy_manager_at_import():
    """OnboardingManager() builds CaddyProxyManager, which runs sudo mkdir.

    Unit jobs use plain python:* images without sudo. organizations.py also
    constructs OnboardingManager at import time, so patch before any router import.
    """
    mock_caddy = MagicMock()
    with (
        patch("modules.onboarding_manager.CaddyProxyManager", return_value=mock_caddy),
        patch("backend.modules.onboarding_manager.CaddyProxyManager", return_value=mock_caddy),
    ):
        yield


# --- Live appliance fixtures (integration / contract) ---


@pytest.fixture(scope="session")
def appliance_base_url() -> str:
    return os.environ.get("APPLIANCE_BASE_URL", DEFAULT_BASE_URL).rstrip("/")


@pytest.fixture(scope="session")
def admin_jwt(appliance_base_url: str) -> str:
    password = os.environ.get("APPLIANCE_ADMIN_PASSWORD", "").strip()
    if not password:
        pytest.skip("APPLIANCE_ADMIN_PASSWORD is not set")
    with httpx.Client(verify=False, timeout=60.0) as client:
        resp = client.post(
            f"{appliance_base_url}/auth/token",
            json={"password": password},
        )
        if resp.status_code != 200:
            pytest.skip(
                f"Could not obtain JWT from {appliance_base_url}/auth/token "
                f"(status {resp.status_code})"
            )
        token = resp.json().get("access_token")
        if not token:
            pytest.skip("Auth response missing access_token")
        return str(token)


@pytest.fixture(scope="session")
def api_client(appliance_base_url: str, admin_jwt: str):
    with httpx.Client(
        base_url=appliance_base_url,
        headers={"Authorization": f"Bearer {admin_jwt}"},
        verify=False,
        timeout=120.0,
    ) as client:
        yield client
