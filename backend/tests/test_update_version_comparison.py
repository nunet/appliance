import json

from backend.modules import utils


def test_is_remote_version_newer_prefers_dpkg_result(monkeypatch):
    monkeypatch.setattr(utils, "_dpkg_lt_version", lambda current, latest: True)
    assert utils._is_remote_version_newer("v0.9.1-22-7c4ca4ee", "0.9.1-22-7c4ca4eec0")


def test_is_remote_version_newer_handles_equal_values(monkeypatch):
    monkeypatch.setattr(utils, "_dpkg_lt_version", lambda current, latest: None)
    assert not utils._is_remote_version_newer("v0.14.1", "0.14.1")


def test_is_remote_version_newer_falls_back_to_semver(monkeypatch):
    monkeypatch.setattr(utils, "_dpkg_lt_version", lambda current, latest: None)
    assert utils._is_remote_version_newer("0.14.0", "0.14.1")
    assert not utils._is_remote_version_newer("0.14.2", "0.14.1")


def test_get_updates_uses_new_comparator(monkeypatch):
    monkeypatch.setattr(utils, "get_appliance_version", lambda: "0.14.1-1")
    monkeypatch.setattr(utils, "_dpkg_lt_version", lambda current, latest: True)
    monkeypatch.setattr(
        utils,
        "_build_update_details",
        lambda kind: {
            "environment": "production",
            "channel": "stable",
            "resolved_channel": "stable",
            "fell_back": False,
            "latest": "0.14.1-2",
        },
    )

    payload = json.loads(utils.get_appliance_updates())
    assert payload["available"] is True
    assert payload["current"] == "0.14.1-1"
    assert payload["latest"] == "0.14.1-2"
