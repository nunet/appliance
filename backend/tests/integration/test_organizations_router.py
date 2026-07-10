"""Integration tests for organizations router touchpoints."""

import pytest

pytestmark = pytest.mark.integration


def test_known_organizations(api_client):
    resp = api_client.get("/organizations/known")
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, dict)


def test_onboarding_status(api_client):
    resp = api_client.get("/organizations/status")
    assert resp.status_code == 200


def test_onboarding_steps(api_client):
    resp = api_client.get("/organizations/steps")
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, (list, dict))


def test_joined_organizations(api_client):
    resp = api_client.get("/organizations/joined")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
