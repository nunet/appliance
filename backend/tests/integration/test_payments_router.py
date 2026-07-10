"""Integration tests for payments router against a live appliance."""

import pytest

pytestmark = pytest.mark.integration


def test_payments_config_shape(api_client):
    resp = api_client.get("/payments/config")
    assert resp.status_code == 200
    body = resp.json()
    assert "ethereum" in body
    assert "cardano" in body
    eth = body["ethereum"]
    assert "chain_id" in eth
    assert "token_symbol" in eth
    assert "token_decimals" in eth


def test_list_payments_response_shape(api_client):
    resp = api_client.get("/payments/list_payments")
    assert resp.status_code == 200
    body = resp.json()
    for key in ("total_count", "paid_count", "unpaid_count", "ignored_count", "items"):
        assert key in body
    assert isinstance(body["items"], list)
