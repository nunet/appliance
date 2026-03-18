import importlib
import json
import sys
import types


def _reload_utils(monkeypatch, env_value: str):
    monkeypatch.setenv("APPLIANCE_ENV", env_value)
    import backend.modules.environment_profile as env_profile
    importlib.reload(env_profile)

    import backend.modules.utils as utils
    return importlib.reload(utils)


def _install_stub_dms_manager(monkeypatch, version: str):
    module = types.ModuleType("modules.dms_manager")

    class DummyDMSManager:
        def get_dms_version(self) -> str:
            return version

    module.DMSManager = DummyDMSManager
    monkeypatch.setitem(sys.modules, "modules.dms_manager", module)


def test_production_prefers_stable_and_falls_back_for_appliance(monkeypatch):
    utils = _reload_utils(monkeypatch, env_value="production")
    _install_stub_dms_manager(monkeypatch, version="0.9.0")

    monkeypatch.setattr(utils, "detect_deb_arch", lambda: "amd64")
    monkeypatch.setattr(utils, "get_appliance_version", lambda: "0.8.0")
    monkeypatch.setattr(utils, "_fetch_registry_version", lambda kind: "")

    calls: list[str] = []

    def fake_deb_version(url: str, cache_key: str) -> str:
        calls.append(cache_key)
        if "nunet-appliance-web-amd64-stable.deb" in url:
            return ""
        if "nunet-appliance-web-amd64-latest.deb" in url:
            return "0.9.0"
        if "nunet-dms-amd64-stable.deb" in url:
            return "1.0.0"
        if "nunet-dms-amd64-latest.deb" in url:
            return "1.0.1"
        return ""

    monkeypatch.setattr(utils, "_deb_version_from_url", fake_deb_version)

    appliance_update = json.loads(utils.get_appliance_updates())
    dms_update = json.loads(utils.get_dms_updates())

    assert appliance_update["environment"] == "production"
    assert appliance_update["channel"] == "stable"
    assert appliance_update["resolved_channel"] == "latest"
    assert appliance_update["latest"] == "0.9.0"
    assert appliance_update["available"] is True

    assert dms_update["environment"] == "production"
    assert dms_update["channel"] == "stable"
    assert dms_update["resolved_channel"] == "stable"
    assert dms_update["latest"] == "1.0.0"

    assert "appliance:amd64:stable" in calls
    assert "appliance:amd64:latest" in calls


def test_staging_uses_latest_channel_for_updates(monkeypatch):
    utils = _reload_utils(monkeypatch, env_value="staging")
    _install_stub_dms_manager(monkeypatch, version="0.9.0")

    monkeypatch.setattr(utils, "detect_deb_arch", lambda: "amd64")
    monkeypatch.setattr(utils, "get_appliance_version", lambda: "0.8.0")
    monkeypatch.setattr(utils, "_fetch_registry_version", lambda kind: "")

    def fake_deb_version(url: str, cache_key: str) -> str:
        if "-latest.deb" in url:
            return "1.2.3"
        return ""

    monkeypatch.setattr(utils, "_deb_version_from_url", fake_deb_version)

    appliance_update = json.loads(utils.get_appliance_updates())
    dms_update = json.loads(utils.get_dms_updates())

    assert appliance_update["environment"] == "staging"
    assert appliance_update["channel"] == "latest"
    assert appliance_update["resolved_channel"] == "latest"
    assert appliance_update["latest"] == "1.2.3"

    assert dms_update["environment"] == "staging"
    assert dms_update["channel"] == "latest"
    assert dms_update["resolved_channel"] == "latest"
