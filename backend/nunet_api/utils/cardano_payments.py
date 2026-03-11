"""
Server-side Cardano payment helpers using Koios (preprod) and pycardano.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from fractions import Fraction
from typing import Any, Dict, List, Optional, Sequence, Union

import requests
from pycardano import Address, TransactionBuilder, Transaction, TransactionWitnessSet
from pycardano.backend.base import ChainContext, GenesisParameters, ProtocolParameters
from pycardano.exception import (
    InsufficientUTxOBalanceException,
    InvalidArgumentException,
    TransactionBuilderException,
    TransactionFailedException,
    UTxOSelectionException,
)
from pycardano.hash import ScriptHash
from pycardano.network import Network
from pycardano.transaction import (
    Asset,
    AssetName,
    MultiAsset,
    TransactionBody,
    TransactionInput,
    TransactionOutput,
    UTxO,
    Value,
)
from pycardano.utils import min_lovelace_post_alonzo

DEFAULT_TIMEOUT = 15

# Defensive: pycardano Value sometimes gets constructed with multi_asset=None; normalize globally
_orig_value_init = Value.__init__
_orig_value_from_primitive = Value.from_primitive.__func__  # unwrap classmethod


def _safe_value_init(self, coin: int = 0, multi_asset: Optional[MultiAsset] = None):
    if multi_asset is None:
        multi_asset = MultiAsset()
    return _orig_value_init(self, coin, multi_asset)


Value.__init__ = _safe_value_init  # type: ignore[assignment]
def _safe_value_from_primitive(cls, values):
    v = _orig_value_from_primitive(cls, values)
    if getattr(v, "multi_asset", None) is None:
        v.multi_asset = MultiAsset()
    return v


Value.from_primitive = classmethod(_safe_value_from_primitive)  # type: ignore[assignment]

# Also guard arithmetic on Value to avoid None multi_asset during internal pycardano ops
_orig_value_add = Value.__add__
_orig_value_sub = Value.__sub__


def _safe_value_add(self, other):
    result = _orig_value_add(self, other)
    if getattr(result, "multi_asset", None) is None:
        result = Value(result.coin, MultiAsset())
    return result


def _safe_value_sub(self, other):
    result = _orig_value_sub(self, other)
    if getattr(result, "multi_asset", None) is None:
        result = Value(result.coin, MultiAsset())
    return result


Value.__add__ = _safe_value_add  # type: ignore[assignment]
Value.__sub__ = _safe_value_sub  # type: ignore[assignment]

# Defensive: ensure TransactionOutput always receives Value with a MultiAsset
_orig_tx_output_init = TransactionOutput.__init__
_orig_tx_output_from_primitive = TransactionOutput.from_primitive.__func__  # unwrap classmethod


def _normalize_amount(amount: Union[Value, int]) -> Value:
    if isinstance(amount, Value):
        if getattr(amount, "multi_asset", None) is None:
            return Value(amount.coin, MultiAsset())
        return amount
    return Value(int(amount), MultiAsset())


def _safe_tx_output_init(
    self,
    address,
    amount,
    datum_hash=None,
    datum=None,
    script=None,
    post_alonzo=False,
    *args,
    **kwargs,
):
    """
    Accepts the canonical TransactionOutput args but is lenient to pycardano
    internals that may pass extra positional/keyword parameters in newer
    versions (e.g., script_ref, reference scripts). We only care about the
    first 5 fields for our use-case and ignore the rest.
    """
    # map stray positional arguments if they were provided
    extra = list(args)
    if extra:
        if datum_hash is None:
            datum_hash = extra.pop(0)
        if extra and datum is None:
            datum = extra.pop(0)
        if extra and script is None:
            script = extra.pop(0)
        if extra and post_alonzo is False:
            try:
                post_alonzo = bool(extra.pop(0))
            except Exception:
                pass
        # ignore any remaining extras

    # tolerate alternative keyword forms
    if "script_ref" in kwargs and script is None:
        script = kwargs.pop("script_ref")
    if "reference_script" in kwargs and script is None:
        script = kwargs.pop("reference_script")
    # normalize amount into a Value with MultiAsset
    amount = _normalize_amount(amount)
    return _orig_tx_output_init(
        self,
        address,
        amount,
        datum_hash,
        datum,
        script,
        post_alonzo,
    )


def _safe_tx_output_from_primitive(cls, value):
    out = _orig_tx_output_from_primitive(cls, value)
    out.amount = _normalize_amount(out.amount)
    return out


TransactionOutput.__init__ = _safe_tx_output_init  # type: ignore[assignment]
TransactionOutput.from_primitive = classmethod(_safe_tx_output_from_primitive)  # type: ignore[assignment]

# Guard validation paths so type checks do not fail when upstream hands us
# Value(amount, multi_asset=None) instances.
_orig_value_validate = Value.validate
_orig_tx_output_validate = TransactionOutput.validate


def _safe_value_validate(self):
    if getattr(self, "multi_asset", None) is None:
        self.multi_asset = MultiAsset()
    return _orig_value_validate(self)


def _safe_tx_output_validate(self):
    self.amount = _normalize_amount(self.amount)
    return _orig_tx_output_validate(self)


Value.validate = _safe_value_validate  # type: ignore[assignment]
TransactionOutput.validate = _safe_tx_output_validate  # type: ignore[assignment]


class CardanoTxBuildError(Exception):
    """Raised when we cannot build a Cardano transaction."""


def _decimal_to_fraction(value: Union[str, float, int]) -> Fraction:
    try:
        return Fraction(str(value))
    except Exception:
        return Fraction(0)


def _parse_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def decode_cbor_hex(hex_str: str) -> bytes:
    normalized = (hex_str or "").strip().lower()
    if normalized.startswith("0x"):
        normalized = normalized[2:]
    return bytes.fromhex(normalized)


def _token_amount(amount: str, decimals: int) -> int:
    try:
        dec = Decimal(amount)
    except (InvalidOperation, TypeError):
        raise CardanoTxBuildError("Invalid amount format")
    quantized = dec.quantize(Decimal(10) ** -decimals)
    if quantized != dec:
        raise CardanoTxBuildError(f"Amount exceeds allowed decimals ({decimals})")
    if quantized < 0:
        raise CardanoTxBuildError("Amount must be positive")
    if decimals == 0:
        return int(quantized)
    return int(quantized * (10**decimals))


def _cost_model_as_dict(raw_cost_model: Optional[Dict[str, Any]]) -> Dict[str, Dict[str, int]]:
    if not isinstance(raw_cost_model, dict):
        return {}
    models: Dict[str, Dict[str, int]] = {}
    for key, val in raw_cost_model.items():
        if isinstance(val, dict):
            models[key] = {str(k): int(v) for k, v in val.items() if isinstance(v, (int, float, str))}
        # Koios sometimes returns arrays; keep them untouched but wrapped to satisfy type hints.
        elif isinstance(val, Sequence):
            try:
                models[key] = {str(i): int(v) for i, v in enumerate(val)}
            except Exception:
                models[key] = {}
    return models


class KoiosChainContext(ChainContext):
    """
    Lightweight ChainContext backed by Koios REST (preprod).
    Implements the minimal surface TransactionBuilder needs for basic transfers.
    """

    def __init__(self, base_url: str, network: Network = Network.TESTNET) -> None:
        self.base_url = base_url.rstrip("/")
        self._network = network
        self._tip: Optional[Dict[str, Any]] = None
        self._protocol_param: Optional[ProtocolParameters] = None
        self._genesis_param: Optional[GenesisParameters] = None

    def _post(self, path: str, payload: Optional[Dict[str, Any]] = None) -> Any:
        url = f"{self.base_url}{path}"
        try:
            res = requests.post(url, json=payload or {}, timeout=DEFAULT_TIMEOUT)
            res.raise_for_status()
            return res.json()
        except requests.HTTPError as exc:
            detail = ""
            try:
                detail = res.text or ""
            except Exception:
                detail = ""
            msg = f"Koios POST {path} failed: {exc}"
            if detail:
                msg = f"{msg}; body: {detail}"
            raise TransactionFailedException(msg) from exc

    @property
    def protocol_param(self) -> ProtocolParameters:
        if self._protocol_param is None:
            params = self._post("/epoch_params") or []
            if not params:
                raise TransactionFailedException("Koios epoch_params returned empty payload")
            latest = params[0]
            coins_per_utxo_word = _parse_int(latest.get("coins_per_utxo_size"), 4310)
            cost_models = _cost_model_as_dict(latest.get("cost_models"))
            self._protocol_param = ProtocolParameters(
                min_fee_constant=_parse_int(latest.get("min_fee_b")),
                min_fee_coefficient=_parse_int(latest.get("min_fee_a")),
                max_block_size=_parse_int(latest.get("max_block_size")),
                max_tx_size=_parse_int(latest.get("max_tx_size")),
                max_block_header_size=_parse_int(latest.get("max_bh_size")),
                key_deposit=_parse_int(latest.get("key_deposit")),
                pool_deposit=_parse_int(latest.get("pool_deposit")),
                pool_influence=_decimal_to_fraction(latest.get("influence")),
                monetary_expansion=_decimal_to_fraction(latest.get("monetary_expand_rate")),
                treasury_expansion=_decimal_to_fraction(latest.get("treasury_growth_rate")),
                decentralization_param=_decimal_to_fraction(latest.get("decentralisation")),
                extra_entropy=str(latest.get("extra_entropy") or ""),
                protocol_major_version=_parse_int(latest.get("protocol_major")),
                protocol_minor_version=_parse_int(latest.get("protocol_minor")),
                min_utxo=_parse_int(latest.get("min_utxo_value")),
                min_pool_cost=_parse_int(latest.get("min_pool_cost")),
                price_mem=_decimal_to_fraction(latest.get("price_mem")),
                price_step=_decimal_to_fraction(latest.get("price_step")),
                max_tx_ex_mem=_parse_int(latest.get("max_tx_ex_mem")),
                max_tx_ex_steps=_parse_int(latest.get("max_tx_ex_steps")),
                max_block_ex_mem=_parse_int(latest.get("max_block_ex_mem")),
                max_block_ex_steps=_parse_int(latest.get("max_block_ex_steps")),
                max_val_size=_parse_int(latest.get("max_val_size")),
                collateral_percent=_parse_int(latest.get("collateral_percent")),
                max_collateral_inputs=_parse_int(latest.get("max_collateral_inputs")),
                coins_per_utxo_word=coins_per_utxo_word,
                coins_per_utxo_byte=coins_per_utxo_word,
                cost_models=cost_models,
            )
        return self._protocol_param

    @property
    def genesis_param(self) -> GenesisParameters:
        if self._genesis_param is None:
            data = self._post("/genesis") or []
            if not data:
                raise TransactionFailedException("Koios genesis endpoint returned empty payload")
            raw = data[0]
            alonzo = raw.get("alonzogenesis")
            coins_per_word = None
            if isinstance(alonzo, str):
                try:
                    alonzo_json = json.loads(alonzo)
                    coins_per_word = _parse_int(alonzo_json.get("lovelacePerUTxOWord"))
                except Exception:
                    coins_per_word = None
            self._genesis_param = GenesisParameters(
                active_slots_coefficient=_decimal_to_fraction(raw.get("activeslotcoeff")),
                update_quorum=_parse_int(raw.get("updatequorum")),
                max_lovelace_supply=_parse_int(raw.get("maxlovelacesupply")),
                network_magic=_parse_int(raw.get("networkmagic")),
                epoch_length=_parse_int(raw.get("epochlength")),
                system_start=_parse_int(raw.get("systemstart")),
                slots_per_kes_period=_parse_int(raw.get("slotsperkesperiod")),
                slot_length=_parse_int(raw.get("slotlength")),
                max_kes_evolutions=_parse_int(raw.get("maxkesrevolutions")),
                security_param=_parse_int(raw.get("securityparam")),
            )
            # Keep protocol param coins_per_utxo_word in sync when genesis has it
            if coins_per_word and self._protocol_param:
                self._protocol_param.coins_per_utxo_word = coins_per_word
        return self._genesis_param

    @property
    def network(self) -> Network:
        return self._network

    @property
    def epoch(self) -> int:
        return _parse_int(self._tip_info().get("epoch_no"))

    @property
    def last_block_slot(self) -> int:
        return _parse_int(self._tip_info().get("abs_slot"))

    def _tip_info(self) -> Dict[str, Any]:
        if self._tip is None:
            tip = self._post("/tip") or []
            if not tip:
                raise TransactionFailedException("Koios tip endpoint returned empty payload")
            self._tip = tip[0]
        return self._tip

    def _utxos(self, address: str) -> List[UTxO]:
        payload = {"_addresses": [address]}
        data = self._post("/address_info", payload) or []
        if not data:
            return []
        entry = data[0]
        utxo_set = entry.get("utxo_set") or []
        addr_obj = Address.from_primitive(address)
        utxos: List[UTxO] = []
        for utxo in utxo_set:
            tx_hash = utxo.get("tx_hash")
            tx_index = _parse_int(utxo.get("tx_index"))
            if not tx_hash:
                continue
            tx_input = TransactionInput.from_primitive([bytes.fromhex(tx_hash), tx_index])
            multi_asset = MultiAsset()
            asset_list = utxo.get("asset_list") or []
            for asset in asset_list:
                policy_id = asset.get("policy_id")
                asset_name_hex = asset.get("asset_name") or asset.get("asset_name_hex")
                quantity = _parse_int(asset.get("quantity"))
                if not policy_id or not asset_name_hex or quantity <= 0:
                    continue
                policy = ScriptHash.from_primitive(bytes.fromhex(policy_id))
                asset_name = AssetName.from_primitive(bytes.fromhex(asset_name_hex))
                policy_assets = multi_asset.get(policy, Asset())
                policy_assets[asset_name] = policy_assets.get(asset_name, 0) + quantity
                multi_asset[policy] = policy_assets
            value = Value(_parse_int(utxo.get("value")), multi_asset if len(multi_asset) else None)
            if value.multi_asset is None:
                value = Value(value.coin, MultiAsset())
            tx_output = TransactionOutput(addr_obj, value)
            utxos.append(UTxO(tx_input, tx_output))
        return utxos

    def submit_tx_cbor(self, cbor: Union[bytes, str]):
        """
        Koios expects raw CBOR bytes with Content-Type application/cbor.
        """
        if isinstance(cbor, bytes):
            raw = cbor
        elif isinstance(cbor, str):
            tx_hex = cbor[2:] if cbor.startswith("0x") else cbor
            raw = bytes.fromhex(tx_hex)
        else:
            raise InvalidArgumentException("Transaction CBOR must be bytes or hex string")

        url = f"{self.base_url}/submittx"

        def _attempt(content_type: str, body: Union[bytes, str]):
            return requests.post(
                url,
                data=body,
                headers={"Content-Type": content_type},
                timeout=DEFAULT_TIMEOUT,
            )

        last_exc: Optional[Exception] = None
        res = None
        # Try canonical CBOR first, then octet-stream, then JSON hex as a fallback.
        for content_type, body in (
            ("application/cbor", raw),
            ("application/octet-stream", raw),
            ("application/json", json.dumps({"tx": raw.hex()})),
        ):
            try:
                res = _attempt(content_type, body)
                res.raise_for_status()
                break
            except requests.HTTPError as exc:
                last_exc = exc
                # If not 415, bail immediately.
                if res is not None and res.status_code != 415:
                    break
                continue
        if res is None:
            raise TransactionFailedException("Koios submit failed: no response object")
        if last_exc:
            body = ""
            try:
                body = res.text
            except Exception:
                body = ""
            msg = f"Koios POST /submittx failed: {last_exc}"
            if body:
                msg = f"{msg}; body: {body}"
            raise TransactionFailedException(msg) from last_exc

        # Koios typically returns a JSON array with the tx hash
        try:
            result = res.json()
        except Exception:
            result = res.text

        if isinstance(result, list) and result:
            entry = result[0]
            if isinstance(entry, dict) and entry.get("error"):
                raise TransactionFailedException(str(entry.get("error")))
            if isinstance(entry, str):
                return entry
        if isinstance(result, str) and result:
            return result
        return result

    def evaluate_tx_cbor(self, cbor: Union[bytes, str]):
        # Plutus evaluation not needed for basic transfers right now.
        raise TransactionFailedException("evaluate_tx is not supported for this backend")


@dataclass
class CardanoBuildResult:
    tx: Transaction
    tx_body: TransactionBody
    fee_lovelace: int
    tx_hash: str


class CardanoPaymentsBuilder:
    def __init__(self, token_config: Dict[str, Any], koios_base_url: str) -> None:
        self.token_config = token_config
        self.context = KoiosChainContext(koios_base_url, network=Network.TESTNET)

    def _make_value(self, amount: str) -> Value:
        decimals = int(self.token_config.get("token_decimals", 0))
        units = _token_amount(amount, decimals)
        policy_id = self.token_config["policy_id"]
        asset_name_hex = self.token_config["asset_name_hex"]
        policy = ScriptHash.from_primitive(bytes.fromhex(policy_id))
        asset_name = AssetName.from_primitive(bytes.fromhex(asset_name_hex))
        asset = Asset({asset_name: units})
        multi_asset = MultiAsset({policy: asset})
        return Value(0, multi_asset)

    def _balance_summary(self, utxos: List[UTxO]) -> Dict[str, int]:
        policy_id = self.token_config["policy_id"]
        asset_name_hex = self.token_config["asset_name_hex"]
        policy = ScriptHash.from_primitive(bytes.fromhex(policy_id))
        asset_name = AssetName.from_primitive(bytes.fromhex(asset_name_hex))
        lovelace = 0
        tokens = 0
        for utxo in utxos:
            lovelace += int(utxo.output.amount.coin)
            ma = utxo.output.amount.multi_asset or MultiAsset()
            if policy in ma:
                tokens += int(ma[policy].get(asset_name, 0))
        return {"lovelace": lovelace, "tokens": tokens}

    def build_unsigned_tx(
        self,
        from_address: str,
        to_address: str,
        amount: str,
        change_address: Optional[str] = None,
    ) -> CardanoBuildResult:
        try:
            decimals = int(self.token_config.get("token_decimals", 0))
            units_needed = _token_amount(amount, decimals)
            policy = ScriptHash.from_primitive(bytes.fromhex(self.token_config["policy_id"]))
            asset_name = AssetName.from_primitive(bytes.fromhex(self.token_config["asset_name_hex"]))

            builder = TransactionBuilder(self.context)
            sender = Address.from_primitive(from_address)
            receiver = Address.from_primitive(to_address)
            change = Address.from_primitive(change_address) if change_address else sender
            # Collect UTxOs from sender and, if different, the change address as well.
            utxos = self.context._utxos(str(sender))
            if change != sender:
                extra_utxos = self.context._utxos(str(change))
                # Deduplicate by (tx_hash, idx)
                seen = {(u.input.transaction_id, u.input.index) for u in utxos}
                for u in extra_utxos:
                    key = (u.input.transaction_id, u.input.index)
                    if key not in seen:
                        utxos.append(u)
                        seen.add(key)
            if not utxos:
                raise CardanoTxBuildError("No UTxOs available for the Cardano sender address")
            balance = self._balance_summary(utxos)
            value = self._make_value(amount)
            if not isinstance(value.multi_asset, MultiAsset):
                value = Value(value.coin, value.multi_asset or MultiAsset())
            output = TransactionOutput(receiver, value)
            # Ensure the output carries at least min ADA for multi-asset UTxOs
            min_coin = min_lovelace_post_alonzo(output, self.context)
            if output.amount.coin < min_coin:
                output.amount.coin = min_coin
            # quick pre-checks before invoking the builder
            required_lovelace = min_coin + 800_000  # fee buffer to avoid opaque errors
            if balance["tokens"] < units_needed:
                raise CardanoTxBuildError(
                    f"Insufficient token balance to cover requested amount (have {balance['tokens']}, need {units_needed})"
                )
            if balance["lovelace"] < required_lovelace:
                raise CardanoTxBuildError(
                    f"Insufficient ADA for min-utxo + fees (have {balance['lovelace']} lovelace, need >= {required_lovelace}; min-utxo alone {min_coin})"
                )

            builder.add_input_address(sender)
            if change != sender:
                builder.add_input_address(change)
            builder.add_output(output)
            try:
                tx_body = builder.build(change_address=change)
            except (InsufficientUTxOBalanceException, UTxOSelectionException, TransactionBuilderException) as exc:
                raise CardanoTxBuildError(
                    f"Insufficient UTxOs to cover tokens and fees. Add more ADA (and NTX if needed) to the wallet. "
                    f"Current balance: {balance['lovelace']} lovelace, {balance['tokens']} tokens; "
                    f"Needs: {units_needed} tokens, >= {required_lovelace} lovelace (min-utxo {min_coin})."
                ) from exc
            # Defensive: ensure all outputs carry a MultiAsset instance (pycardano validation can choke on None)
            for idx, out in enumerate(tx_body.outputs):
                amt = out.amount
                if isinstance(amt, Value):
                    if getattr(amt, "multi_asset", None) is None:
                        out.amount = Value(amt.coin, MultiAsset())
                        tx_body.outputs[idx] = out
                else:
                    out.amount = Value(int(amt), MultiAsset())
                    tx_body.outputs[idx] = out

            tx = Transaction(tx_body, TransactionWitnessSet())
            tx_hash = tx_body.hash().hex()
            fee = getattr(tx_body, "fee", None)
            return CardanoBuildResult(
                tx=tx,
                tx_body=tx_body,
                fee_lovelace=int(fee) if fee is not None else 0,
                tx_hash=tx_hash,
            )
        except (
            InvalidArgumentException,
            InsufficientUTxOBalanceException,
            UTxOSelectionException,
            TransactionBuilderException,
        ) as exc:
            raise CardanoTxBuildError(str(exc)) from exc
        except Exception as exc:  # pragma: no cover - defensive
            raise CardanoTxBuildError(str(exc) or "Failed to build Cardano transaction") from exc

    def submit_signed_tx(self, tx_body_cbor: str, witness_set_cbor: str) -> str:
        tx_body = TransactionBody.from_cbor(decode_cbor_hex(tx_body_cbor))
        witness_set = TransactionWitnessSet.from_cbor(decode_cbor_hex(witness_set_cbor))
        tx = Transaction(tx_body, witness_set)
        result = self.context.submit_tx(tx)
        # Koios returns the tx hash on success
        if isinstance(result, str):
            return result
        # fallback to computed hash
        return tx_body.hash().hex()
