"""Runtime environment profile resolution for appliance settings.

This module is imported during API startup and intentionally validates
configuration early so invalid environment setup fails fast.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from typing import Literal, Optional, Tuple, List

APPLIANCE_ENV_VAR = "APPLIANCE_ENV"
DEFAULT_ENV: Literal["production", "staging"] = "production"
VALID_ENVS = {"production", "staging"}

UpdateChannel = Literal["stable", "latest"]
PackageKind = Literal["appliance", "dms"]


@dataclass(frozen=True)
class EthereumTokenConfig:
    chain_id: int
    token_address: str
    token_symbol: str
    token_decimals: int
    explorer_base_url: Optional[str]
    network_name: Optional[str]


@dataclass(frozen=True)
class CardanoTokenConfig:
    chain_id: int
    token_address: str
    token_symbol: str
    token_decimals: int
    explorer_base_url: Optional[str]
    network_name: Optional[str]
    policy_id: str
    asset_name_hex: str
    asset_name: str
    asset_name_encoded: Optional[str]
    asset_id: str


@dataclass(frozen=True)
class UpdateChannelPolicy:
    preferred_channel: UpdateChannel
    fallback_channel: Optional[UpdateChannel] = None


@dataclass(frozen=True)
class RuntimeProfile:
    environment: Literal["production", "staging"]
    ethereum: EthereumTokenConfig
    cardano: CardanoTokenConfig
    cardano_koios_base_url: str
    appliance_updates: UpdateChannelPolicy
    dms_updates: UpdateChannelPolicy


def _read_appliance_env() -> Literal["production", "staging"]:
    raw = os.getenv(APPLIANCE_ENV_VAR)
    if raw is None or not raw.strip():
        return DEFAULT_ENV
    value = raw.strip()
    if value not in VALID_ENVS:
        allowed = ", ".join(sorted(VALID_ENVS))
        raise ValueError(
            f"Invalid {APPLIANCE_ENV_VAR}={raw!r}. Expected one of: {allowed}."
        )
    return value  # type: ignore[return-value]


def _parse_int_override(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw.strip())
    except ValueError as exc:
        raise ValueError(f"Invalid integer value for {name}: {raw!r}") from exc


def _parse_str_override(name: str, default: str) -> str:
    raw = os.getenv(name)
    if raw is None:
        return default
    value = raw.strip()
    return value or default


def _parse_optional_str_override(name: str, default: Optional[str]) -> Optional[str]:
    raw = os.getenv(name)
    if raw is None:
        return default
    value = raw.strip()
    return value or default


def _production_eth_defaults() -> EthereumTokenConfig:
    return EthereumTokenConfig(
        chain_id=1,
        token_address="0xF0d33BeDa4d734C72684b5f9abBEbf715D0a7935",
        token_symbol="NTX",
        token_decimals=16,
        explorer_base_url="https://etherscan.io/",
        network_name="Ethereum Mainnet",
    )


def _staging_eth_defaults() -> EthereumTokenConfig:
    return EthereumTokenConfig(
        chain_id=11155111,
        token_address="0xB37216b70a745129966E553cF8Ee2C51e1cB359A",
        token_symbol="TSTNTX",
        token_decimals=16,
        explorer_base_url="https://sepolia.etherscan.io/",
        network_name="Ethereum Sepolia",
    )

def _production_cardano_defaults() -> CardanoTokenConfig:
    return CardanoTokenConfig(
        chain_id=1,
        token_address="asset19yuner2nz27pq9pjdta50xwfyd0d2nry2l6lvu",
        token_symbol="NTX",
        token_decimals=16,
        explorer_base_url="https://cexplorer.io/",
        network_name="Cardano Mainnet",
        policy_id="edfd7a1d77bcb8b884c474bdc92a16002d1fb720e454fa6e99344479",
        asset_name_hex="4e5458",
        asset_name="NTX",
        asset_name_encoded="4e5458",
        asset_id="asset19yuner2nz27pq9pjdta50xwfyd0d2nry2l6lvu",
    )

def _staging_cardano_defaults() -> CardanoTokenConfig:
    return CardanoTokenConfig(
        chain_id=1,
        token_address="asset1tkxzxjklvs5gdkpuh26ex3re4rl8wjg3wmyxdr",
        token_symbol="tNTX",
        token_decimals=16,
        explorer_base_url="https://preprod.cexplorer.io/",
        network_name="Cardano Preprod",
        policy_id="88b60b51a3dcd3a6134bb1c0fdd2837d8cc87abd27dbd0c3a494869f",
        asset_name_hex="4e754e657450726570726f64",
        asset_name="NuNetPreprod",
        asset_name_encoded="4e754e657450726570726f64",
        asset_id="asset1tkxzxjklvs5gdkpuh26ex3re4rl8wjg3wmyxdr",
    )


def _apply_staging_eth_overrides(base: EthereumTokenConfig) -> EthereumTokenConfig:
    return EthereumTokenConfig(
        chain_id=_parse_int_override("APPLIANCE_STAGING_ETH_CHAIN_ID", base.chain_id),
        token_address=_parse_str_override(
            "APPLIANCE_STAGING_ETH_TOKEN_ADDRESS", base.token_address
        ),
        token_symbol=_parse_str_override(
            "APPLIANCE_STAGING_ETH_TOKEN_SYMBOL", base.token_symbol
        ),
        token_decimals=_parse_int_override(
            "APPLIANCE_STAGING_ETH_TOKEN_DECIMALS", base.token_decimals
        ),
        explorer_base_url=_parse_optional_str_override(
            "APPLIANCE_STAGING_ETH_EXPLORER_BASE_URL", base.explorer_base_url
        ),
        network_name=_parse_optional_str_override(
            "APPLIANCE_STAGING_ETH_NETWORK_NAME", base.network_name
        ),
    )


def _apply_staging_cardano_overrides(base: CardanoTokenConfig) -> CardanoTokenConfig:
    return CardanoTokenConfig(
        chain_id=_parse_int_override(
            "APPLIANCE_STAGING_CARDANO_CHAIN_ID", base.chain_id
        ),
        token_address=_parse_str_override(
            "APPLIANCE_STAGING_CARDANO_TOKEN_ADDRESS", base.token_address
        ),
        token_symbol=_parse_str_override(
            "APPLIANCE_STAGING_CARDANO_TOKEN_SYMBOL", base.token_symbol
        ),
        token_decimals=_parse_int_override(
            "APPLIANCE_STAGING_CARDANO_TOKEN_DECIMALS", base.token_decimals
        ),
        explorer_base_url=_parse_optional_str_override(
            "APPLIANCE_STAGING_CARDANO_EXPLORER_BASE_URL", base.explorer_base_url
        ),
        network_name=_parse_optional_str_override(
            "APPLIANCE_STAGING_CARDANO_NETWORK_NAME", base.network_name
        ),
        policy_id=_parse_str_override(
            "APPLIANCE_STAGING_CARDANO_POLICY_ID", base.policy_id
        ),
        asset_name_hex=_parse_str_override(
            "APPLIANCE_STAGING_CARDANO_ASSET_NAME_HEX", base.asset_name_hex
        ),
        asset_name=_parse_str_override(
            "APPLIANCE_STAGING_CARDANO_ASSET_NAME", base.asset_name
        ),
        asset_name_encoded=_parse_optional_str_override(
            "APPLIANCE_STAGING_CARDANO_ASSET_NAME_ENCODED", base.asset_name_encoded
        ),
        asset_id=_parse_str_override(
            "APPLIANCE_STAGING_CARDANO_ASSET_ID", base.asset_id
        ),
    )


def _build_profile() -> RuntimeProfile:
    environment = _read_appliance_env()

    if environment == "staging":
        eth = _apply_staging_eth_overrides(_staging_eth_defaults())
        cardano = _apply_staging_cardano_overrides(_staging_cardano_defaults())
        koios_base = _parse_str_override(
            "APPLIANCE_STAGING_CARDANO_KOIOS_BASE_URL",
            "https://preprod.koios.rest/api/v1",
        )
        return RuntimeProfile(
            environment="staging",
            ethereum=eth,
            cardano=cardano,
            cardano_koios_base_url=koios_base,
            appliance_updates=UpdateChannelPolicy(preferred_channel="latest"),
            dms_updates=UpdateChannelPolicy(preferred_channel="latest"),
        )

    return RuntimeProfile(
        environment="production",
        ethereum=_production_eth_defaults(),
        cardano=_production_cardano_defaults(),
        cardano_koios_base_url="https://api.koios.rest/api/v1",
        appliance_updates=UpdateChannelPolicy(
            preferred_channel="stable",
            fallback_channel="latest",
        ),
        dms_updates=UpdateChannelPolicy(
            preferred_channel="stable",
            fallback_channel="latest",
        ),
    )


def normalize_arch(raw_arch: str) -> Optional[str]:
    value = (raw_arch or "").strip().lower()
    if value in {"amd64", "x86_64", "x64"}:
        return "amd64"
    if value in {"arm64", "aarch64", "aarch64_be"}:
        return "arm64"
    return None


def detect_deb_arch() -> Optional[str]:
    try:
        result = subprocess.run(
            ["dpkg", "--print-architecture"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            normalized = normalize_arch((result.stdout or "").strip())
            if normalized:
                return normalized
    except Exception:
        pass
    return None


def build_package_url(kind: PackageKind, arch: str, channel: UpdateChannel) -> str:
    if kind == "appliance":
        return f"https://d.nunet.io/nunet-appliance-web-{arch}-{channel}.deb"
    return f"https://d.nunet.io/nunet-dms-{arch}-{channel}.deb"


def iter_package_candidates(
    kind: PackageKind,
    arch: str,
    policy: UpdateChannelPolicy,
) -> List[Tuple[UpdateChannel, str]]:
    candidates: List[Tuple[UpdateChannel, str]] = [
        (policy.preferred_channel, build_package_url(kind, arch, policy.preferred_channel))
    ]
    if policy.fallback_channel and policy.fallback_channel != policy.preferred_channel:
        candidates.append(
            (policy.fallback_channel, build_package_url(kind, arch, policy.fallback_channel))
        )
    return candidates


RUNTIME_PROFILE = _build_profile()


def get_runtime_profile() -> RuntimeProfile:
    return RUNTIME_PROFILE
