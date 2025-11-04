# nunet_api/routers/payments.py
from typing import List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException
from decimal import Decimal, InvalidOperation
import re
from ..schemas import (
    TokenConfig,
    PaymentReportIn,
    PaymentReportOut,
)
from modules.dms_manager import DMSManager

router = APIRouter()

# --------- hard-coded token config (Just for testing for now) ---------
PAY_CHAIN_ID = 11155111  # Sepolia chain ID
PAY_TOKEN_ADDRESS = "0xB37216b70a745129966E553cF8Ee2C51e1cB359A"  
PAY_TOKEN_DECIMALS = 6
PAY_TOKEN_SYMBOL = "TSTNTX"
PAY_EXPLORER_BASE = "https://sepolia.etherscan.io/"
PAY_NETWORK_NAME = "Ethereum Sepolia"
PAY_BLOCKCHAIN = "ETHEREUM"
ALLOWED_BLOCKCHAINS = {"ETHEREUM", "CARDANO"}
# --------------------------------------------------------------

def get_mgr():
    return DMSManager()

def _get_token_config() -> TokenConfig:
    if not PAY_TOKEN_ADDRESS or not PAY_CHAIN_ID:
        raise HTTPException(status_code=500, detail="Token config not set")
    return TokenConfig(
        chain_id=PAY_CHAIN_ID,
        token_address=PAY_TOKEN_ADDRESS,
        token_symbol=PAY_TOKEN_SYMBOL,
        token_decimals=PAY_TOKEN_DECIMALS,
        explorer_base_url=PAY_EXPLORER_BASE,
        network_name=PAY_NETWORK_NAME,
    )

# --- Utilities ---

_addr_re = re.compile(r"^0x[a-fA-F0-9]{40}$")
_txhash_re = re.compile(r"^0x[a-fA-F0-9]{64}$")

def _is_evm_address(addr: str) -> bool:
    return bool(addr) and bool(_addr_re.match(addr))

def _valid_amount_str(amount: str, max_decimals: int) -> bool:
    try:
        d = Decimal(amount)
        if d < 0:
            return False
        frac = -d.as_tuple().exponent if d.as_tuple().exponent < 0 else 0
        return frac <= max_decimals
    except (InvalidOperation, TypeError):
        return False

def _norm_tx_keys(d: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize DMS transaction keys (handles TitleCase and snake_case).
    """
    if not isinstance(d, dict):
        return {}
    return {
        "unique_id": d.get("unique_id") or d.get("UniqueID") or d.get("uniqueId") or "",
        "payment_validator_did": d.get("payment_validator_did") or d.get("PaymentValidatorDID") or "",
        "contract_did": d.get("contract_did") or d.get("ContractDID") or "",
        "to_address": d.get("to_address") or d.get("ToAddress") or "",
        "amount": d.get("amount") or d.get("Amount") or "",
        "status": (d.get("status") or d.get("Status") or "").lower(),  # normalize to lower
        "tx_hash": d.get("tx_hash") or d.get("TxHash") or "",
    }

# status sort: "unpaid" first then "paid" (updated requirement)
def _status_rank(status: str) -> int:
    s = (status or "").lower()
    return 0 if s == "unpaid" else 1 if s == "paid" else 99

# --- Routes ---

@router.get("/config", response_model=TokenConfig)
def get_config():
    """
    Static token/network config for the UI.
    """
    return _get_token_config()

@router.get("/list_payments", response_model=Dict[str, Any])
def list_payments(mgr: DMSManager = Depends(get_mgr)):
    """
    Fetch all transactions from DMS, normalize, validate lightly,
    sort by status (paid first, then unpaid), and return counts.
    """
    out = mgr.list_transactions(blockchain=PAY_BLOCKCHAIN)
    if out.get("status") == "error":
        raise HTTPException(status_code=502, detail=out.get("message", "DMS list transactions failed"))
    raw = out.get("transactions", []) or []
    # Normalize each row (skip non-dicts safely)
    normed: List[Dict[str, Any]] = []
    for row in raw:
        if isinstance(row, dict):
            tx = _norm_tx_keys(row)
            # light sanity checks (do not block dev flow)
            if tx["to_address"] and not _is_evm_address(tx["to_address"]):
                # accept but you can choose to skip
                pass
            if tx["amount"] and not _valid_amount_str(tx["amount"], PAY_TOKEN_DECIMALS):
                pass
            normed.append(tx)

    # sort: unpaid first, then paid
    normed.sort(key=lambda t: (_status_rank(t.get("status", "")), t.get("unique_id", "")))

    # counts
    total = len(normed)
    paid_count = sum(1 for t in normed if t.get("status") == "paid")
    unpaid_count = sum(1 for t in normed if t.get("status") == "unpaid")

    return {
        "total_count": total,
        "paid_count": paid_count,
        "unpaid_count": unpaid_count,
        "items": normed,
    }

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
    print(body)
    # Call DMS confirm; payment_provider maps to unique_id
    blockchain = (body.blockchain or PAY_BLOCKCHAIN).strip().upper()
    if blockchain not in ALLOWED_BLOCKCHAINS:
        raise HTTPException(status_code=400, detail="Unsupported blockchain")

    dms_res = mgr.confirm_transaction(
        unique_id=body.payment_provider,
        tx_hash=body.tx_hash,
        blockchain=blockchain,
    )
    if dms_res.get("status") != "success":
        raise HTTPException(status_code=502, detail=dms_res.get("message", "DMS confirm failed"))

    return PaymentReportOut(
        tx_hash=body.tx_hash,
        to_address=addr,
        amount=body.amount,
        payment_provider=body.payment_provider,
        blockchain=blockchain,
    )
