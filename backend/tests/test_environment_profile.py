import importlib

import pytest


def _reload_environment_profile(monkeypatch, env_value=None):
    if env_value is None:
        monkeypatch.delenv("APPLIANCE_ENV", raising=False)
    else:
        monkeypatch.setenv("APPLIANCE_ENV", env_value)
    import backend.modules.environment_profile as environment_profile

    return importlib.reload(environment_profile)


def test_environment_profile_defaults_to_production(monkeypatch):
    profile_module = _reload_environment_profile(monkeypatch, env_value=None)
    profile = profile_module.get_runtime_profile()

    assert profile.environment == "production"
    assert profile.appliance_updates.preferred_channel == "stable"
    assert profile.appliance_updates.fallback_channel == "latest"
    assert profile.ethereum.chain_id == 1
    assert profile.ethereum.network_name == "Ethereum Mainnet"


def test_environment_profile_accepts_staging(monkeypatch):
    profile_module = _reload_environment_profile(monkeypatch, env_value="staging")
    profile = profile_module.get_runtime_profile()

    assert profile.environment == "staging"
    assert profile.appliance_updates.preferred_channel == "latest"
    assert profile.appliance_updates.fallback_channel is None
    assert profile.ethereum.chain_id == 11155111
    assert profile.ethereum.network_name == "Ethereum Sepolia"


@pytest.mark.parametrize("invalid_value", ["prod", "stage", "DEV", "invalid"])
def test_environment_profile_rejects_non_canonical_values(monkeypatch, invalid_value):
    monkeypatch.setenv("APPLIANCE_ENV", invalid_value)
    import backend.modules.environment_profile as environment_profile

    with pytest.raises(ValueError):
        importlib.reload(environment_profile)
