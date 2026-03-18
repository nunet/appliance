import importlib


STAGING_OVERRIDE_KEYS = [
    "APPLIANCE_STAGING_ETH_CHAIN_ID",
    "APPLIANCE_STAGING_ETH_TOKEN_ADDRESS",
    "APPLIANCE_STAGING_ETH_TOKEN_SYMBOL",
    "APPLIANCE_STAGING_ETH_TOKEN_DECIMALS",
    "APPLIANCE_STAGING_ETH_EXPLORER_BASE_URL",
    "APPLIANCE_STAGING_ETH_NETWORK_NAME",
    "APPLIANCE_STAGING_CARDANO_CHAIN_ID",
    "APPLIANCE_STAGING_CARDANO_TOKEN_ADDRESS",
    "APPLIANCE_STAGING_CARDANO_TOKEN_SYMBOL",
    "APPLIANCE_STAGING_CARDANO_TOKEN_DECIMALS",
    "APPLIANCE_STAGING_CARDANO_EXPLORER_BASE_URL",
    "APPLIANCE_STAGING_CARDANO_NETWORK_NAME",
    "APPLIANCE_STAGING_CARDANO_POLICY_ID",
    "APPLIANCE_STAGING_CARDANO_ASSET_NAME_HEX",
    "APPLIANCE_STAGING_CARDANO_ASSET_NAME",
    "APPLIANCE_STAGING_CARDANO_ASSET_NAME_ENCODED",
    "APPLIANCE_STAGING_CARDANO_ASSET_ID",
    "APPLIANCE_STAGING_CARDANO_KOIOS_BASE_URL",
]


def _reload_payments_router(monkeypatch, env_value: str, overrides: dict[str, str] | None = None):
    monkeypatch.setenv("APPLIANCE_ENV", env_value)
    for key in STAGING_OVERRIDE_KEYS:
        monkeypatch.delenv(key, raising=False)
    for key, value in (overrides or {}).items():
        monkeypatch.setenv(key, value)

    import modules.environment_profile as env_profile
    importlib.reload(env_profile)

    import backend.nunet_api.routers.payments as payments_router
    return importlib.reload(payments_router)


def test_production_payments_config_uses_mainnet_values(monkeypatch):
    payments_router = _reload_payments_router(monkeypatch, env_value="production")

    eth = payments_router.PAYMENTS_CONFIG.ethereum
    assert eth.chain_id == 1
    assert eth.token_address == "0xF0d33BeDa4d734C72684b5f9abBEbf715D0a7935"
    assert eth.token_symbol == "NTX"
    assert eth.explorer_base_url == "https://etherscan.io/"
    assert eth.network_name == "Ethereum Mainnet"


def test_staging_payments_config_uses_sepolia_defaults(monkeypatch):
    payments_router = _reload_payments_router(monkeypatch, env_value="staging")

    eth = payments_router.PAYMENTS_CONFIG.ethereum
    assert eth.chain_id == 11155111
    assert eth.token_address == "0xB37216b70a745129966E553cF8Ee2C51e1cB359A"
    assert eth.token_symbol == "TSTNTX"
    assert eth.explorer_base_url == "https://sepolia.etherscan.io/"
    assert eth.network_name == "Ethereum Sepolia"


def test_staging_eth_overrides_are_applied(monkeypatch):
    payments_router = _reload_payments_router(
        monkeypatch,
        env_value="staging",
        overrides={
            "APPLIANCE_STAGING_ETH_CHAIN_ID": "10",
            "APPLIANCE_STAGING_ETH_TOKEN_ADDRESS": "0x1111111111111111111111111111111111111111",
            "APPLIANCE_STAGING_ETH_TOKEN_SYMBOL": "OVR",
            "APPLIANCE_STAGING_ETH_TOKEN_DECIMALS": "9",
            "APPLIANCE_STAGING_ETH_EXPLORER_BASE_URL": "https://example.explorer/",
            "APPLIANCE_STAGING_ETH_NETWORK_NAME": "OverrideNet",
        },
    )

    eth = payments_router.PAYMENTS_CONFIG.ethereum
    assert eth.chain_id == 10
    assert eth.token_address == "0x1111111111111111111111111111111111111111"
    assert eth.token_symbol == "OVR"
    assert eth.token_decimals == 9
    assert eth.explorer_base_url == "https://example.explorer/"
    assert eth.network_name == "OverrideNet"


def test_cardano_defaults_are_used_as_fallback_in_both_envs(monkeypatch):
    prod_router = _reload_payments_router(monkeypatch, env_value="production")
    prod_cardano = prod_router.PAYMENTS_CONFIG.cardano

    staging_router = _reload_payments_router(monkeypatch, env_value="staging")
    staging_cardano = staging_router.PAYMENTS_CONFIG.cardano

    assert staging_cardano.chain_id == prod_cardano.chain_id
    assert staging_cardano.token_address == prod_cardano.token_address
    assert staging_cardano.token_symbol == prod_cardano.token_symbol
    assert staging_cardano.explorer_base_url == prod_cardano.explorer_base_url
    assert staging_cardano.network_name == prod_cardano.network_name
