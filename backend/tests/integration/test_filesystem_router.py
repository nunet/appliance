"""Integration tests for filesystem router."""

import pytest

pytestmark = pytest.mark.integration

DEFAULT_ROOT = "/home/ubuntu"


def test_list_home_ubuntu_roots(api_client):
    resp = api_client.get("/filesystem/list", params={"path": DEFAULT_ROOT})
    assert resp.status_code == 200
    body = resp.json()
    items = body.get("items") or []
    names = {e.get("name") for e in items if isinstance(e, dict)}
    for expected in ("contracts", "ensembles", "nunet"):
        assert expected in names, f"missing allowlisted root {expected}"
