# nunet_api/routers/payments.py
from typing import List, Dict, Any, Tuple, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pycardano.exception import TransactionFailedException
from decimal import Decimal, InvalidOperation
import json
import re
from ..schemas import (
    CardanoBuildRequest,
    CardanoBuildResponse,
    CardanoSubmitRequest,
    CardanoSubmitResponse,
    CardanoTokenConfig,
    PaymentQuoteCancelRequest,
    PaymentQuoteCancelResponse,
    PaymentQuoteGetRequest,
    PaymentQuoteGetResponse,
    PaymentQuoteValidateRequest,
    PaymentQuoteValidateResponse,
    PaymentReportIn,
    PaymentReportOut,
    PaymentsConfig,
    TokenConfig,
)
from modules.dms_manager import DMSManager
from modules.environment_profile import get_runtime_profile
from ..utils.cardano_payments import CardanoPaymentsBuilder, CardanoTxBuildError

router = APIRouter()

# --------- environment-scoped token configs ---------
RUNTIME_PROFILE = get_runtime_profile()

ETH_TOKEN_CONFIG = TokenConfig(
    chain_id=RUNTIME_PROFILE.ethereum.chain_id,
    token_address=RUNTIME_PROFILE.ethereum.token_address,
    token_symbol=RUNTIME_PROFILE.ethereum.token_symbol,
    token_decimals=RUNTIME_PROFILE.ethereum.token_decimals,
    explorer_base_url=RUNTIME_PROFILE.ethereum.explorer_base_url,
    network_name=RUNTIME_PROFILE.ethereum.network_name,
)

CARDANO_TOKEN_CONFIG = CardanoTokenConfig(
    chain_id=RUNTIME_PROFILE.cardano.chain_id,
    token_address=RUNTIME_PROFILE.cardano.token_address,
    token_decimals=RUNTIME_PROFILE.cardano.token_decimals,
    token_symbol=RUNTIME_PROFILE.cardano.token_symbol,
    explorer_base_url=RUNTIME_PROFILE.cardano.explorer_base_url,
    network_name=RUNTIME_PROFILE.cardano.network_name,
    policy_id=RUNTIME_PROFILE.cardano.policy_id,
    asset_name_hex=RUNTIME_PROFILE.cardano.asset_name_hex,
    asset_name=RUNTIME_PROFILE.cardano.asset_name,
    asset_name_encoded=RUNTIME_PROFILE.cardano.asset_name_encoded,
    asset_id=RUNTIME_PROFILE.cardano.asset_id,
)

PAYMENTS_CONFIG = PaymentsConfig(ethereum=ETH_TOKEN_CONFIG, cardano=CARDANO_TOKEN_CONFIG)
PAY_BLOCKCHAIN = "ETHEREUM"
ALLOWED_BLOCKCHAINS = {"ETHEREUM", "CARDANO"}
CARDANO_KOIOS_BASE = RUNTIME_PROFILE.cardano_koios_base_url
MAX_DECIMALS_BY_CHAIN = {
    "ETHEREUM": ETH_TOKEN_CONFIG.token_decimals,
    "CARDANO": CARDANO_TOKEN_CONFIG.token_decimals,
}
# --------------------------------------------------------------

def get_mgr():
    return DMSManager()


def _get_cardano_builder() -> CardanoPaymentsBuilder:
    return CardanoPaymentsBuilder(CARDANO_TOKEN_CONFIG.model_dump(), CARDANO_KOIOS_BASE)

def _get_payments_config() -> PaymentsConfig:
    return PAYMENTS_CONFIG

# --- Utilities ---

_addr_re = re.compile(r"^0x[a-fA-F0-9]{40}$")
_txhash_re = re.compile(r"^0x[a-fA-F0-9]{64}$")
_cardano_re = re.compile(r"^(addr|stake)[0-9a-zA-Z_]{10,}$")


def _is_evm_address(addr: str) -> bool:
    return bool(addr) and bool(_addr_re.match(addr))


def _is_cardano_address(addr: str) -> bool:
    return bool(addr) and bool(_cardano_re.match(addr))


def _is_supported_address(addr: str) -> bool:
    normalized = (addr or "").strip()
    if not normalized:
        return False
    return _is_evm_address(normalized) or _is_cardano_address(normalized)


def _is_address_for_blockchain(addr: str, blockchain: str) -> bool:
    bc = (blockchain or "").upper()
    if bc == "CARDANO":
        return _is_cardano_address(addr)
    if bc == "ETHEREUM":
        return _is_evm_address(addr)
    return _is_supported_address(addr)

def _valid_amount_str(amount: str, max_decimals: int) -> bool:
    try:
        d = Decimal(amount)
        if d < 0:
            return False
        quantized = d.quantize(Decimal(10) ** -max_decimals)
        if quantized != d:
            return False
        frac = -quantized.as_tuple().exponent if quantized.as_tuple().exponent < 0 else 0
        return frac <= max_decimals
    except (InvalidOperation, TypeError):
        return False

def _coerce_first_address(
    value: Any,
    preferred_keys: Tuple[str, ...] = ("provider_addr", "requester_addr", "address", "addr"),
    allow_plain_string: bool = True,
) -> str:
    """
    Ensure the to_address field is a plain string.
    DMS responses sometimes provide structured payloads, so search through
    nested collections for the first non-empty string.
    """
    if isinstance(value, str):
        if not allow_plain_string:
            return ""
        return value.strip()
    if isinstance(value, dict):
        for key in preferred_keys:
            candidate = value.get(key)
            if isinstance(candidate, str):
                trimmed = candidate.strip()
                if trimmed:
                    return trimmed
        return ""
    if isinstance(value, (list, tuple)):
        for entry in value:
            coerced = _coerce_first_address(entry, preferred_keys, allow_plain_string=allow_plain_string)
            if coerced:
                return coerced
        return ""
    return ""


def _extract_blockchain(value: Any, default: str = PAY_BLOCKCHAIN) -> str:
    """
    Discover blockchain hint from nested DMS payloads.
    """
    if isinstance(value, dict):
        bc = value.get("blockchain") or value.get("chain")
        if isinstance(bc, str) and bc.strip():
            return bc.strip().upper()
    if isinstance(value, (list, tuple)):
        for entry in value:
            bc = _extract_blockchain(entry, "")
            if bc:
                return bc
    return (default or PAY_BLOCKCHAIN).upper()


def _coerce_metadata(value: Any) -> Optional[Dict[str, Any]]:
    """
    Normalize optional metadata payload into a dictionary.
    Accepts native dicts and JSON-object strings.
    """
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return None
        if isinstance(parsed, dict):
            return parsed
    return None


def _coerce_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes", "y"}:
            return True
        if lowered in {"false", "0", "no", "n"}:
            return False
    if isinstance(value, (int, float)):
        return bool(value)
    return default


def _norm_tx_keys(d: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize DMS transaction keys (handles TitleCase and snake_case).
    """
    if not isinstance(d, dict):
        return {}
    to_address_raw = d.get("to_address") or d.get("ToAddress") or d.get("toAddress") or ""
    blockchain = _extract_blockchain(to_address_raw, d.get("blockchain") or PAY_BLOCKCHAIN)
    metadata_raw = d.get("metadata")
    if metadata_raw is None:
        metadata_raw = d.get("Metadata")
    metadata = _coerce_metadata(metadata_raw)
    requires_conversion_raw = (
        d.get("requires_conversion")
        if "requires_conversion" in d
        else d.get("RequiresConversion")
        if "RequiresConversion" in d
        else d.get("requiresConversion")
    )
    created_at_raw = d.get("created_at")
    if created_at_raw is None:
        created_at_raw = d.get("CreatedAt")
    if created_at_raw is None:
        created_at_raw = d.get("createdAt")

    unique_id = (
        d.get("unique_id")
        or d.get("UniqueID")
        or d.get("uniqueId")
        or ""
    )

    return {
        "unique_id": unique_id,
        "payment_validator_did": d.get("payment_validator_did") or d.get("PaymentValidatorDID") or "",
        "contract_did": d.get("contract_did") or d.get("ContractDID") or "",
        "to_address": (
            _coerce_first_address(to_address_raw, ("requester_addr", "address", "addr"))
            if unique_id and "orchestration-fee" in unique_id
            else _coerce_first_address(to_address_raw, ("provider_addr", "address", "addr"))
        ),
        "from_address": (
            ""
            if unique_id and "orchestration-fee" in unique_id
            else _coerce_first_address(to_address_raw,
                ("requester_addr", "address", "addr"),
                allow_plain_string=False,
            )
        ),
        "amount": d.get("amount") or d.get("Amount") or "",
        "status": (d.get("status") or d.get("Status") or "").lower(),  # normalize to lower
        "tx_hash": d.get("tx_hash") or d.get("TxHash") or "",
        "blockchain": blockchain,
        "metadata": metadata,
        "original_amount": d.get("original_amount") or d.get("OriginalAmount") or d.get("originalAmount") or "",
        "pricing_currency": d.get("pricing_currency") or d.get("PricingCurrency") or d.get("pricingCurrency") or "",
        "requires_conversion": _coerce_bool(requires_conversion_raw, False),
        "created_at": str(created_at_raw).strip() if created_at_raw is not None else "",
    }


def _validate_tx(tx: Dict[str, Any]) -> Tuple[bool, List[str]]:
    reasons: List[str] = []
    if not tx.get("unique_id"):
        reasons.append("missing unique_id")
    status = tx.get("status")
    if status not in {"paid", "unpaid"}:
        reasons.append("invalid status")
    blockchain = (tx.get("blockchain") or PAY_BLOCKCHAIN).upper()
    if blockchain not in ALLOWED_BLOCKCHAINS:
        reasons.append("unsupported blockchain")
    max_decimals = MAX_DECIMALS_BY_CHAIN.get(blockchain, ETH_TOKEN_CONFIG.token_decimals)
    amount = tx.get("amount")
    if not amount or not _valid_amount_str(str(amount), max_decimals):
        reasons.append("invalid amount")
    address = tx.get("to_address", "")
    if not address:
        reasons.append("missing destination address")
    elif not _is_address_for_blockchain(str(address), blockchain):
        reasons.append("unsupported address format")
    return (not reasons, reasons)

# status sort: "unpaid" first then "paid" (updated requirement)
def _status_rank(status: str) -> int:
    s = (status or "").lower()
    return 0 if s == "unpaid" else 1 if s == "paid" else 99

# --- Routes ---

@router.get("/config", response_model=PaymentsConfig)
def get_config():
    """
    Static token/network config for the UI (EVM + Cardano).
    """
    return _get_payments_config()

def _list_payments_query_has_filters(
    limit: Optional[int],
    offset: Optional[int],
    sort: Optional[str],
    status: Optional[str],
    contract_did: Optional[str],
    unique_id: Optional[str],
    deployment_id: Optional[str],
    blockchain: Optional[str],
    to_address: Optional[str],
    from_address: Optional[str],
    tx_hash: Optional[str],
) -> bool:
    if limit is not None or offset is not None:
        return True
    if sort is not None and sort.strip():
        return True
    if status is not None and status.strip():
        return True
    if contract_did is not None and contract_did.strip():
        return True
    if unique_id is not None and unique_id.strip():
        return True
    if deployment_id is not None and deployment_id.strip():
        return True
    if blockchain is not None and blockchain.strip():
        return True
    if to_address is not None and to_address.strip():
        return True
    if from_address is not None and from_address.strip():
        return True
    if tx_hash is not None and tx_hash.strip():
        return True
    return False


def _parse_status_csv(status: Optional[str]) -> Optional[List[str]]:
    if not status or not str(status).strip():
        return None
    parts = [p.strip() for p in str(status).split(",") if p.strip()]
    return parts or None


@router.get("/list_payments", response_model=Dict[str, Any])
def list_payments(
    limit: Optional[int] = Query(None, ge=0),
    offset: Optional[int] = Query(None, ge=0),
    sort: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    contract_did: Optional[str] = Query(None),
    unique_id: Optional[str] = Query(None),
    deployment_id: Optional[str] = Query(None),
    blockchain: Optional[str] = Query(None),
    to_address: Optional[str] = Query(None),
    from_address: Optional[str] = Query(None),
    tx_hash: Optional[str] = Query(None),
    mgr: DMSManager = Depends(get_mgr),
):
    """
    Fetch transactions from DMS, normalize, validate lightly.

    Without query params: returns all transactions, sorted unpaid-first (legacy).

    With limit, offset, sort, status (comma-separated), and/or contract_did:
    forwards flags to DMS; counts reflect the current page/result set only.
    If ``sort`` is set, ordering follows DMS; otherwise DMS default order is kept.
    """
    has_filters = _list_payments_query_has_filters(
        limit,
        offset,
        sort,
        status,
        contract_did,
        unique_id,
        deployment_id,
        blockchain,
        to_address,
        from_address,
        tx_hash,
    )
    sort_arg = sort.strip() if sort and sort.strip() else None
    status_vals = _parse_status_csv(status)

    if has_filters:
        out = mgr.list_transactions(
            blockchain=blockchain.strip() if blockchain and blockchain.strip() else None,
            limit=limit,
            offset=offset,
            sort=sort_arg,
            contract_did=contract_did.strip() if contract_did and contract_did.strip() else None,
            status=status_vals,
            unique_id=unique_id.strip() if unique_id and unique_id.strip() else None,
            deployment_id=deployment_id.strip() if deployment_id and deployment_id.strip() else None,
            to_address=to_address.strip() if to_address and to_address.strip() else None,
            from_address=from_address.strip() if from_address and from_address.strip() else None,
            tx_hash=tx_hash.strip() if tx_hash and tx_hash.strip() else None,
        )
    else:
        out = mgr.list_transactions(blockchain=None)

    if out.get("status") == "error":
        raise HTTPException(status_code=502, detail=out.get("message", "DMS list transactions failed"))
    raw = out.get("transactions", []) or []
    # Normalize each row (skip non-dicts safely)
    normed: List[Dict[str, Any]] = []
    ignored: List[Dict[str, str]] = []
    for row in raw:
        if isinstance(row, dict):
            tx = _norm_tx_keys(row)
            valid, reasons = _validate_tx(tx)
            if not valid:
                ignored.append(
                    {
                        "unique_id": tx.get("unique_id") or row.get("unique_id") or "",
                        "reason": "; ".join(reasons) or "invalid transaction payload",
                    }
                )
                continue
            normed.append(tx)
        else:
            ignored.append({"unique_id": "", "reason": "transaction is not an object"})

    if not has_filters:
        # sort: unpaid first, then paid (legacy)
        normed.sort(key=lambda t: (_status_rank(t.get("status", "")), t.get("unique_id", "")))
    elif not sort_arg:
        # Filtered request without explicit sort: keep DMS row order
        pass

    # total should prefer DMS-reported filtered total when available.
    total_raw = out.get("total")
    total = int(total_raw) if isinstance(total_raw, (int, float)) and total_raw >= 0 else len(normed)
    paid_count = sum(1 for t in normed if t.get("status") == "paid")
    unpaid_count = sum(1 for t in normed if t.get("status") == "unpaid")

    return {
        "total_count": total,
        "paid_count": paid_count,
        "unpaid_count": unpaid_count,
        "items": normed,
        "ignored_count": len(ignored),
        "ignored": ignored,
    }


@router.post("/quote/get", response_model=PaymentQuoteGetResponse)
def get_payment_quote(body: PaymentQuoteGetRequest, mgr: DMSManager = Depends(get_mgr)):
    result = mgr.get_payment_quote(body.unique_id, body.dest)
    if result.get("status") != "success":
        message = result.get("message", "Failed to get payment quote")
        status_code = 409 if isinstance(message, str) and "active quote already exists" in message.lower() else 502
        raise HTTPException(status_code=status_code, detail=message)
    if not result.get("quote_id") or not result.get("expires_at"):
        raise HTTPException(status_code=502, detail="Invalid quote response from DMS")
    return PaymentQuoteGetResponse(
        quote_id=str(result.get("quote_id") or ""),
        original_amount=str(result.get("original_amount") or ""),
        converted_amount=str(result.get("converted_amount") or ""),
        pricing_currency=str(result.get("pricing_currency") or ""),
        payment_currency=str(result.get("payment_currency") or ""),
        exchange_rate=str(result.get("exchange_rate") or ""),
        expires_at=result.get("expires_at"),
    )


@router.post("/quote/validate", response_model=PaymentQuoteValidateResponse)
def validate_payment_quote(body: PaymentQuoteValidateRequest, mgr: DMSManager = Depends(get_mgr)):
    result = mgr.validate_payment_quote(body.quote_id, body.dest)
    if result.get("status") != "success":
        raise HTTPException(status_code=502, detail=result.get("message", "Failed to validate payment quote"))

    return PaymentQuoteValidateResponse(
        valid=bool(result.get("valid", False)),
        quote_id=result.get("quote_id"),
        original_amount=result.get("original_amount"),
        converted_amount=result.get("converted_amount"),
        pricing_currency=result.get("pricing_currency"),
        payment_currency=result.get("payment_currency"),
        exchange_rate=result.get("exchange_rate"),
        expires_at=result.get("expires_at"),
        error=result.get("error"),
    )


@router.post("/quote/cancel", response_model=PaymentQuoteCancelResponse)
def cancel_payment_quote(body: PaymentQuoteCancelRequest, mgr: DMSManager = Depends(get_mgr)):
    result = mgr.cancel_payment_quote(body.quote_id, body.dest)
    if result.get("status") != "success":
        raise HTTPException(status_code=502, detail=result.get("message", "Failed to cancel payment quote"))
    return PaymentQuoteCancelResponse(status="success")


@router.post("/cardano/build", response_model=CardanoBuildResponse)
def build_cardano_tx(body: CardanoBuildRequest):
    """
    Build an unsigned Cardano transaction server-side using Koios data.
    """
    builder = _get_cardano_builder()
    try:
        res = builder.build_unsigned_tx(
            from_address=body.from_address,
            to_address=body.to_address,
            amount=body.amount,
            change_address=body.change_address or body.from_address,
        )
    except CardanoTxBuildError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except TransactionFailedException as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc) or "Failed to build Cardano transaction")

    return CardanoBuildResponse(
        tx_cbor=res.tx.to_cbor().hex(),
        tx_body_cbor=res.tx_body.to_cbor().hex(),
        tx_hash=res.tx_hash,
        fee_lovelace=str(res.fee_lovelace),
        network=CARDANO_TOKEN_CONFIG.network_name or "Cardano",
    )


@router.post("/cardano/submit", response_model=CardanoSubmitResponse)
def submit_cardano_tx(body: CardanoSubmitRequest, mgr: DMSManager = Depends(get_mgr)):
    """
    Accept a wallet-produced witness set, stitch the transaction, submit via Koios,
    then confirm in DMS.
    """
    builder = _get_cardano_builder()
    try:
        tx_hash = builder.submit_signed_tx(body.tx_body_cbor, body.witness_set_cbor)
    except (CardanoTxBuildError, TransactionFailedException) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:
        raise HTTPException(status_code=502, detail="Failed to submit Cardano transaction")

    dms_res = mgr.confirm_transaction(
        unique_id=body.payment_provider,
        tx_hash=tx_hash,
        blockchain="CARDANO",
        quote_id=body.quote_id,
    )
    if dms_res.get("status") != "success":
        raise HTTPException(status_code=502, detail=dms_res.get("message", "DMS confirm failed"))

    return CardanoSubmitResponse(
        tx_hash=tx_hash,
        to_address=body.to_address,
        amount=body.amount,
        payment_provider=body.payment_provider,
        blockchain="CARDANO",
        quote_id=body.quote_id,
        fee_lovelace=None,
    )

@router.post("/report_to_dms", response_model=PaymentReportOut)
def report_to_dms(body: PaymentReportIn, mgr: DMSManager = Depends(get_mgr)):
    """
    FE reports a completed on-chain tx.
    We confirm it in DMS using:
      nunet actor cmd --context user /dms/tokenomics/contract/transactions/confirm
        --unique-id <payment_provider> --tx-hash <tx_hash>

    Returns the same 4 fields back.
    """
    
    # normalize address form (allow bare 40-hex without 0x in dev data)
    addr = body.to_address.strip()
    if not addr.startswith("0x") and len(addr) == 40:
        addr = "0x" + addr

    # basic validation of hash (non-blocking for early dev)
    if body.tx_hash and not _txhash_re.match(body.tx_hash):
        # raise HTTPException(status_code=400, detail="Invalid tx_hash format")
        pass
    # Call DMS confirm; payment_provider maps to unique_id
    blockchain = (body.blockchain or PAY_BLOCKCHAIN).strip().upper()
    if blockchain not in ALLOWED_BLOCKCHAINS:
        raise HTTPException(status_code=400, detail="Unsupported blockchain")

    dms_res = mgr.confirm_transaction(
        unique_id=body.payment_provider,
        tx_hash=body.tx_hash,
        blockchain=blockchain,
        quote_id=body.quote_id,
    )
    if dms_res.get("status") != "success":
        raise HTTPException(status_code=502, detail=dms_res.get("message", "DMS confirm failed"))

    return PaymentReportOut(
        tx_hash=body.tx_hash,
        to_address=addr,
        amount=body.amount,
        payment_provider=body.payment_provider,
        blockchain=blockchain,
        quote_id=body.quote_id,
    )
