"""Integration tests for DMS status endpoints."""

import pytest

pytestmark = pytest.mark.integration


def test_dms_status(api_client):
    resp = api_client.get("/dms/status")
    assert resp.status_code == 200
    body = resp.json()
    for key in ("dms_status", "dms_running", "dms_peer_id"):
        assert key in body


def test_dms_status_full(api_client):
    resp = api_client.get("/dms/status/full")
    assert resp.status_code == 200
    body = resp.json()
    for key in (
        "onboarding_status",
        "free_resources",
        "allocated_resources",
        "onboarded_resources",
    ):
        assert key in body
