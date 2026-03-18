import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from modules.path_constants import ROLE_METADATA_FILE

logger = logging.getLogger(__name__)


def _default_payload() -> Dict[str, Any]:
    return {"organizations": {}}


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_role_metadata() -> Dict[str, Any]:
    """
    Load cached role metadata from disk.
    Returns a structure with an ``organizations`` mapping.
    """
    try:
        with ROLE_METADATA_FILE.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        if not isinstance(data, dict):
            raise ValueError("Role metadata must be a JSON object")
    except FileNotFoundError:
        return _default_payload()
    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning("Failed reading %s: %s", ROLE_METADATA_FILE, exc)
        return _default_payload()

    data.setdefault("organizations", {})
    return data


def _safe_roles(values: Optional[List[Any]]) -> List[str]:
    roles: List[str] = []
    if isinstance(values, (list, tuple, set)):
        for value in values:
            if value is None:
                continue
            text = value.strip() if isinstance(value, str) else str(value).strip()
            if text and text not in roles:
                roles.append(text)
    return roles


def _clean_str(value: Any) -> Optional[str]:
    if isinstance(value, str):
        cleaned = value.strip()
        return cleaned or None
    return None


def save_role_metadata(data: Dict[str, Any]) -> None:
    payload = dict(data or {})
    payload.setdefault("organizations", {})
    ROLE_METADATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = ROLE_METADATA_FILE.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    tmp_path.replace(ROLE_METADATA_FILE)


def record_role_selection(
    org_did: str,
    *,
    org_name: Optional[str],
    roles: List[str],
    primary_role: Optional[str],
    why_join: Optional[str],
    email: Optional[str] = None,
    location: Optional[str] = None,
    discord: Optional[str] = None,
    wormhole: Optional[str] = None,
    wallet_address: Optional[str] = None,
    wallet_chain: Optional[str] = None,
    blockchain: Optional[str] = None,
    renewal: bool = False,
) -> None:
    """
    Persist role selection metadata locally so other services can infer permissions.
    """
    org_did = (org_did or "").strip()
    if not org_did:
        logger.debug("Skipping role metadata update: missing org DID.")
        return

    cleaned_roles = _safe_roles(roles)
    primary = (primary_role or "").strip() or (cleaned_roles[0] if cleaned_roles else None)

    payload = load_role_metadata()
    orgs = payload.setdefault("organizations", {})

    entry = orgs.get(org_did, {})
    if not isinstance(entry, dict):
        entry = {}

    timestamp = _now_iso()
    contact = {
        key: value
        for key, value in {
            "email": _clean_str(email),
            "location": _clean_str(location),
            "discord": _clean_str(discord),
            "wormhole": _clean_str(wormhole),
        }.items()
        if value
    }

    entry.update(
        {
            "name": org_name,
            "roles": cleaned_roles,
            "primary_role": primary,
            "why_join": why_join,
            "contact": contact or entry.get("contact", {}),
            "updated_at": timestamp,
            "wallet_address": wallet_address,
            "wallet_chain": wallet_chain,
            "blockchain": _clean_str(blockchain.lower()) if isinstance(blockchain, str) else None,
        }
    )
    if renewal:
        entry["renewed_at"] = timestamp
    orgs[org_did] = entry
    save_role_metadata(payload)


def record_join_payload(org_did: str, payload: Dict[str, Any]) -> None:
    """
    Store the latest successful join payload so renewals can reuse the inputs.
    """
    org_did = (org_did or "").strip()
    if not org_did:
        return

    sanitized: Dict[str, Any] = {}
    for key, value in (payload or {}).items():
        if value in (None, "", []):
            continue
        if key == "email":
            sanitized[key] = str(value)
            continue
        if key == "roles":
            sanitized[key] = _safe_roles(value if isinstance(value, list) else [value])
            continue
        if key == "wallet_chain" and isinstance(value, str):
            sanitized[key] = value.lower()
            continue
        if key == "blockchain" and isinstance(value, str):
            sanitized[key] = value.lower()
            continue
        if isinstance(value, (str, int, float, bool)):
            sanitized[key] = value
            continue
        if isinstance(value, list):
            sanitized[key] = value
            continue
        try:
            json.dumps(value)
            sanitized[key] = value
        except TypeError:
            sanitized[key] = str(value)

    metadata = load_role_metadata()
    orgs = metadata.setdefault("organizations", {})
    entry = orgs.get(org_did, {})
    if not isinstance(entry, dict):
        entry = {}

    existing = entry.get("last_join_payload") if isinstance(entry.get("last_join_payload"), dict) else {}
    merged = dict(existing)
    merged.update(sanitized)
    entry["last_join_payload"] = merged
    entry["updated_at"] = _now_iso()
    orgs[org_did] = entry
    save_role_metadata(metadata)


def get_join_payload(org_did: str) -> Dict[str, Any]:
    org_did = (org_did or "").strip()
    if not org_did:
        return {}
    entry = load_role_metadata().get("organizations", {}).get(org_did)
    if isinstance(entry, dict):
        payload = entry.get("last_join_payload")
        if isinstance(payload, dict):
            return dict(payload)
    return {}


def record_last_request_id(org_did: str, request_id: Optional[str]) -> None:
    org_did = (org_did or "").strip()
    if not org_did or not request_id:
        return

    metadata = load_role_metadata()
    orgs = metadata.setdefault("organizations", {})
    entry = orgs.get(org_did, {})
    if not isinstance(entry, dict):
        entry = {}
    entry["last_request_id"] = str(request_id)
    entry["updated_at"] = _now_iso()
    orgs[org_did] = entry
    save_role_metadata(metadata)


def record_org_tokenomics(
    org_did: str,
    tokenomics: Optional[Dict[str, Any]],
) -> None:
    org_did = (org_did or "").strip()
    if not org_did:
        return

    payload = load_role_metadata()
    orgs = payload.setdefault("organizations", {})
    entry = orgs.get(org_did, {})
    if not isinstance(entry, dict):
        entry = {}

    entry["tokenomics"] = tokenomics or {}
    entry["updated_at"] = _now_iso()

    orgs[org_did] = entry
    save_role_metadata(payload)


def record_role_tokens(
    org_did: str,
    *,
    provide_token: Optional[str] = None,
    require_generated: bool = False,
) -> None:
    """
    Persist token hints for the organisation after approval.
    Tokens remain in their canonical locations; this metadata only tracks availability.
    """
    org_did = (org_did or "").strip()
    if not org_did:
        return

    payload = load_role_metadata()
    orgs = payload.setdefault("organizations", {})
    entry = orgs.get(org_did, {})
    if not isinstance(entry, dict):
        entry = {}

    if provide_token:
        entry["provide_token_cached"] = True
    if require_generated:
        entry["require_token_generated"] = True
    entry["updated_at"] = _now_iso()

    orgs[org_did] = entry
    save_role_metadata(payload)


def get_primary_role(org_did: str) -> Optional[str]:
    org_did = (org_did or "").strip()
    if not org_did:
        return None
    entry = load_role_metadata().get("organizations", {}).get(org_did)
    if isinstance(entry, dict):
        role = entry.get("primary_role")
        if isinstance(role, str) and role.strip():
            return role.strip()
    return None


def get_roles(org_did: str) -> List[str]:
    org_did = (org_did or "").strip()
    if not org_did:
        return []
    entry = load_role_metadata().get("organizations", {}).get(org_did)
    if isinstance(entry, dict):
        return _safe_roles(entry.get("roles"))
    return []


def remove_org(org_did: str) -> None:
    """
    Remove cached metadata for the specified organisation.
    """
    org_did = (org_did or "").strip()
    if not org_did:
        return

    payload = load_role_metadata()
    orgs = payload.setdefault("organizations", {})
    if orgs.pop(org_did, None) is not None:
        save_role_metadata(payload)


def get_last_request_id(org_did: str) -> Optional[str]:
    org_did = (org_did or "").strip()
    if not org_did:
        return None
    entry = load_role_metadata().get("organizations", {}).get(org_did)
    if isinstance(entry, dict):
        request_id = entry.get("last_request_id")
        if isinstance(request_id, str) and request_id.strip():
            return request_id.strip()
    return None
