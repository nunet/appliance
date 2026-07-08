"""Integration tests for ensemble router (templates and deployments list)."""

import pytest

pytestmark = pytest.mark.integration


def test_list_templates(api_client):
    resp = api_client.get("/ensemble/templates")
    assert resp.status_code == 200
    body = resp.json()
    assert "items" in body
    assert isinstance(body["items"], list)


def test_list_deployments(api_client):
    resp = api_client.get("/ensemble/deployments")
    assert resp.status_code == 200
    body = resp.json()
    assert "items" in body or "deployments" in body or isinstance(body, dict)
