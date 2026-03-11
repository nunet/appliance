# modules/org_utils.py

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple, Optional

try:
    import requests
except ImportError:  # pragma: no cover - optional dependency
    requests = None  # type: ignore[assignment]

from .path_constants import KNOWN_ORGS_FILE, DMS_CAP_FILE



KNOWN_ORGS_SOURCE_URL = (
    "https://gitlab.com/nunet/appliance/-/raw/main/known_orgs/known_organizations.json"
)
KNOWN_ORGS_E2E_FILENAME = "known_organizations.e2e.json"

DEFAULT_ORG_ROLE = "compute_provider"
ROLE_LABELS: Dict[str, str] = {
    "compute_provider": "Compute Provider",
    "orchestrator": "Orchestrator",
    "contract_host": "Contract Host",
    "payment_provider": "Payment Provider",
}
TOKENOMICS_CHAIN_ALLOWLIST = {"cardano", "ethereum"}


def normalize_tokenomics(value: Any) -> Tuple[Optional[Dict[str, Any]], List[str]]:
    """
    Normalise the ``tokenomics`` block. Returns a tuple of
    (sanitised_mapping_or_none, warning_messages).
    """
    warnings: List[str] = []
    if value is None:
        return None, warnings

    if not isinstance(value, dict):
        interpreted = bool(value)
        warnings.append("Tokenomics must be an object; coerced to boolean enabled flag.")
        return {"enabled": interpreted, "chain": None}, warnings

    block = dict(value)

    enabled_raw = block.get("enabled")
    if isinstance(enabled_raw, bool):
        enabled = enabled_raw
    elif enabled_raw is None:
        enabled = False
    else:
        enabled = bool(enabled_raw)
        warnings.append("Tokenomics 'enabled' was coerced to boolean.")
    block["enabled"] = enabled

    chain_raw = block.get("chain")
    chain: Optional[str] = None
    if isinstance(chain_raw, str) and chain_raw.strip():
        chain_candidate = chain_raw.strip().lower()
        if chain_candidate in TOKENOMICS_CHAIN_ALLOWLIST:
            chain = chain_candidate
        else:
            warnings.append(
                f"Tokenomics chain '{chain_raw}' is not supported. Expected one of {sorted(TOKENOMICS_CHAIN_ALLOWLIST)}."
            )
    elif chain_raw not in (None, ""):
        warnings.append("Tokenomics 'chain' must be a string identifier.")
    block["chain"] = chain

    return block, warnings


def get_tokenomics_config(org_entry: Any) -> Dict[str, Any]:
    """
    Return a consistent tokenomics configuration dictionary for an organisation.
    Ensures callers can safely assume ``enabled`` (bool) and ``chain`` (str|None).
    """
    if isinstance(org_entry, dict):
        tokenomics_value = org_entry.get("tokenomics")
        block, _ = normalize_tokenomics(tokenomics_value)
        if block:
            return {
                "enabled": bool(block.get("enabled")),
                "chain": block.get("chain"),
            }
    return {"enabled": False, "chain": None}
def normalize_org_roles(org_entry: Any) -> Tuple[List[str], List[str]]:
    """
    Extract supported role identifiers from an organization entry.
    Returns a tuple of (valid_role_ids, warning_messages). Falls back to
    DEFAULT_ORG_ROLE and records a warning when roles cannot be resolved.
    """
    roles: List[str] = []
    warnings: List[str] = []
    seen_roles: set[str] = set()
    seen_warnings: set[str] = set()

    raw = None

    if isinstance(org_entry, dict):
        raw = org_entry.get("roles")
        if isinstance(raw, list):
            for idx, item in enumerate(raw):
                value: Any = None
                if isinstance(item, str):
                    value = item.strip()
                elif isinstance(item, dict):
                    for key in ("id", "value", "role", "name"):
                        candidate = item.get(key)
                        if isinstance(candidate, str) and candidate.strip():
                            value = candidate.strip()
                            break
                else:
                    value = None

                if not value:
                    msg = f"roles[{idx}] is missing an identifier and was ignored."
                    if msg not in seen_warnings:
                        warnings.append(msg)
                        seen_warnings.add(msg)
                    continue

                if value not in seen_roles:
                    roles.append(value)
                    seen_roles.add(value)
        elif raw not in (None, []):
            msg = "Roles must be provided as a list of role identifiers."
            if msg not in seen_warnings:
                warnings.append(msg)
                seen_warnings.add(msg)

    if not roles:
        fallback_msg = f'Falling back to "{DEFAULT_ORG_ROLE}" due to role configuration issues.'
        if fallback_msg not in seen_warnings:
            warnings.append(fallback_msg)
            seen_warnings.add(fallback_msg)
        roles = [DEFAULT_ORG_ROLE]

    return roles, warnings


def extract_role_profiles(org_entry: Any) -> Dict[str, Dict[str, Any]]:
    """
    Build a mapping of role_id -> role definition for an organization entry.
    Additional fields (permissions, require_template, etc.) are preserved.
    """
    profiles: Dict[str, Dict[str, Any]] = {}

    if not isinstance(org_entry, dict):
        return profiles

    roles = org_entry.get("roles")
    if not isinstance(roles, list):
        return profiles

    for item in roles:
        if not isinstance(item, dict):
            continue
        role_id: str | None = None
        for key in ("id", "value", "role", "name"):
            candidate = item.get(key)
            if isinstance(candidate, str) and candidate.strip():
                role_id = candidate.strip()
                break
        if not role_id:
            continue

        profile = dict(item)
        profile["id"] = role_id
        profiles[role_id] = profile

    return profiles


def load_dms_cap() -> Dict[str, Any]:
    """
    Load the cached capability file (dms.cap). Returns an empty dict if it
    cannot be read.
    """
    try:
        if not DMS_CAP_FILE.exists():
            return {}
        with DMS_CAP_FILE.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except Exception as exc:
        print(f"Failed to load {DMS_CAP_FILE}: {exc}")
        return {}


def get_tokens_for_org(org_did: str) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Return (provide_tokens, require_tokens) for the given organization DID.
    """
    org_did = (org_did or "").strip()
    if not org_did:
        return [], []

    cap_data = load_dms_cap()
    provide_tokens: List[Dict[str, Any]] = []
    require_tokens: List[Dict[str, Any]] = []

    provide_section = cap_data.get("provide") or {}
    provide_list = provide_section.get("tok") if isinstance(provide_section, dict) else None
    if isinstance(provide_list, list):
        for token in provide_list:
            if not isinstance(token, dict):
                continue
            if get_root_issuer(token) == org_did:
                provide_tokens.append(token)

    require_section = cap_data.get("require") or {}
    require_list = require_section.get("tok") if isinstance(require_section, dict) else None
    if isinstance(require_list, list):
        for token in require_list:
            if not isinstance(token, dict):
                continue
            sub_uri = (
                token.get("dms", {})
                .get("sub", {})
                .get("uri")
            )
            if isinstance(sub_uri, str) and sub_uri.strip() == org_did:
                require_tokens.append(token)

    return provide_tokens, require_tokens


def _ensure_roles_payload(payload: Any) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        return {}

    result: Dict[str, Any] = {}

    for did, entry in payload.items():
        if isinstance(entry, dict):
            entry_copy = dict(entry)
            normalized_roles, warnings = normalize_org_roles(entry_copy)
            role_objects: List[Dict[str, Any]] = []
            existing_roles = entry_copy.get("roles")
            for role_id in normalized_roles:
                role_label = ROLE_LABELS.get(role_id, role_id.replace("-", " ").title())
                matched: Dict[str, Any] | None = None

                if isinstance(existing_roles, list):
                    for item in existing_roles:
                        if not isinstance(item, dict):
                            continue
                        for key in ("id", "value", "role", "name"):
                            candidate = item.get(key)
                            if isinstance(candidate, str) and candidate.strip() == role_id:
                                matched = dict(item)
                                break
                        if matched:
                            break

                if matched is None:
                    matched = {"id": role_id, "label": role_label}
                else:
                    matched["id"] = role_id
                    matched.setdefault("label", role_label)

                role_objects.append(matched)

            entry_copy["roles"] = role_objects
            if warnings:
                entry_copy["role_warnings"] = warnings
            else:
                entry_copy.pop("role_warnings", None)

            tokenomics_block, tokenomics_warnings = normalize_tokenomics(entry_copy.get("tokenomics"))
            if tokenomics_block is not None:
                entry_copy["tokenomics"] = tokenomics_block
            else:
                entry_copy.pop("tokenomics", None)
            if tokenomics_warnings:
                entry_copy["tokenomics_warnings"] = tokenomics_warnings
            else:
                entry_copy.pop("tokenomics_warnings", None)

            result[did] = entry_copy
        else:
            result[did] = entry

    return result


def load_known_organizations():
    """
    Load known organizations from known_organizations.json
    Returns:
        dict: {did: name} or {did: {name: ..., ...}} for future extensibility
    """
    candidates = [KNOWN_ORGS_FILE]

    legacy_path = (
        Path.home() / "nunet" / "appliance" / "known_orgs" / "known_organizations.json"
    )
    if legacy_path != KNOWN_ORGS_FILE:
        candidates.append(legacy_path)

    known: Dict[str, Any] = {}
    primary_path: Path | None = None
    for candidate in candidates:
        if candidate.exists():
            with open(candidate, 'r') as f:
                data = json.load(f)
                known = _ensure_roles_payload(data)
                primary_path = candidate
                break

    if primary_path is None:
        primary_path = KNOWN_ORGS_FILE

    e2e_file = primary_path.with_name(KNOWN_ORGS_E2E_FILENAME)
    if e2e_file.exists():
        with open(e2e_file, 'r') as f:
            extra_data = _ensure_roles_payload(json.load(f))
            if isinstance(extra_data, dict):
                known.update(extra_data)

    return known


def refresh_known_organizations(timeout: int = 10) -> Dict[str, Dict[str, object]]:
    """
    Download the latest known organizations file and store it in the repository.

    Returns:
        dict: Parsed known organization mapping.
    Raises:
        requests.RequestException: Network-level errors.
        ValueError: If the payload is not valid JSON/dict.
        OSError: If writing the file fails.
    """
    if requests is None:
        raise RuntimeError("requests library is required to refresh known organizations")
    response = requests.get(KNOWN_ORGS_SOURCE_URL, timeout=timeout)
    response.raise_for_status()

    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError("Known organizations payload should be a JSON object")
    payload = _ensure_roles_payload(payload)

    KNOWN_ORGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(KNOWN_ORGS_FILE, 'w', encoding='utf-8') as f:
        json.dump(payload, f, indent=2)
    try:
        os.chmod(KNOWN_ORGS_FILE, 0o644)
    except PermissionError:
        pass

    legacy_path = (
        Path.home() / "nunet" / "appliance" / "known_orgs" / "known_organizations.json"
    )
    if legacy_path != KNOWN_ORGS_FILE:
        legacy_path.parent.mkdir(parents=True, exist_ok=True)
        with open(legacy_path, 'w', encoding='utf-8') as f:
            json.dump(payload, f, indent=2)
        try:
            os.chmod(legacy_path, 0o644)
        except PermissionError:
            pass

    return payload

def is_organization_known(org_did):
    """
    Check if an organization DID is in the known list
    Args:
        org_did (str): Organization DID to check
    Returns:
        bool: True if known
    """
    known = load_known_organizations()
    return org_did in known

def get_root_issuer(capability):
    """
    Traverse the capability chain to find the ultimate issuer (the organization)
    Args:
        capability (dict): A single capability token under 'provide'
    Returns:
        str: The DID of the ultimate issuer (organization)
    """
    dms_cap = capability.get('dms', {})
    if not isinstance(dms_cap, dict):
        print(" Warning: 'dms cap' is not a dictionary")
        return None
    while True:
        if 'chain' in dms_cap:
            dms_cap = dms_cap['chain']

            # If chain is not a dict, break
            if not isinstance(dms_cap, dict):
                print("Chain is not a dictionary anymore.")
                break

            # If chain has a 'dms' key, dig into it
            if 'dms' in dms_cap:
                dms_cap = dms_cap['dms']
                if not isinstance(dms_cap, dict):
                    print("Warning 'dms cap' inside chain is not a dictionary")
                    break
        else:
            break

    issuer = dms_cap.get('iss', {}).get('uri')
    return issuer

def get_joined_organizations() -> list:
    """
    Extract unique organization DIDs from provide tokens in dms.cap
    Returns:
        list: List of unique organization DIDs
    """
    if not DMS_CAP_FILE.exists():
        return []

    try:
        with DMS_CAP_FILE.open('r') as f:
            data = json.load(f)

        org_dids = set()
        for token in data.get("provide", {}).get("tok", []):
            root_issuer = get_root_issuer(token)
            if root_issuer:
                org_dids.add(root_issuer)

        return list(org_dids)
    except Exception as e:
        # Always return a list, even on error
        print(f"Error getting organisations you have joined: {str(e)}")
        return []

def get_joined_organizations_with_names():
    """
    Get joined organizations with resolved names if available
    Returns:
        list: List of dicts like {"did": "...", "name": "Org Name"}
    """
    if not DMS_CAP_FILE.exists():
        return []

    try:
        with DMS_CAP_FILE.open('r') as f:
            data = json.load(f)
        known_orgs = load_known_organizations()
        result = []
        seen_dids = set()

        # Traverse provide tokens
        for token in data.get("provide", {}).get("tok", []):
            did = get_root_issuer(token)
            if did and did not in seen_dids:
                entry = {"did": did}
                normalized_did = did.strip() 
                org_info = known_orgs.get(normalized_did)
                if isinstance(org_info, dict):
                    entry["name"] = org_info.get("name", "Unknown Organization")
                elif isinstance(org_info, str):
                    entry["name"] = org_info
                else:
                    entry["name"] = "Unknown Organization"
                result.append(entry)
                seen_dids.add(did)
        return result

    except Exception as e:
        # Always return a list, even on error
        print(f"Error getting organisations you have joined: {str(e)}")
        return []

def get_joined_organizations_with_details():
    """
    Get joined organizations with capabilities and expiry dates
    Returns:
        list: List of dicts like {"did": "...", "name": "Org Name", "capabilities": [...], "expiry": "..."}
    """
    if not DMS_CAP_FILE.exists():
        return []

    try:
        with DMS_CAP_FILE.open('r') as f:
            data = json.load(f)
        known_orgs = load_known_organizations()
        result = []
        seen_dids = set()

        # Traverse provide tokens
        for token in data.get("provide", {}).get("tok", []):
            did = get_root_issuer(token)
            if did and did not in seen_dids:
                entry = {"did": did}
                normalized_did = did.strip() 
                org_info = known_orgs.get(normalized_did)
                if isinstance(org_info, dict):
                    entry["name"] = org_info.get("name", "Unknown Organization")
                elif isinstance(org_info, str):
                    entry["name"] = org_info
                else:
                    entry["name"] = "Unknown Organization"
                
                # Extract capabilities and expiry from the token
                dms_cap = token.get('dms', {})
                expiry_raw = dms_cap.get("exp")
                entry["capabilities"] = dms_cap.get("cap", [])
                entry["expiry"] = parse_capability_timestamp(expiry_raw)
                entry["expires_soon"] = capability_expires_within(expiry_raw)
                
                result.append(entry)
                seen_dids.add(did)
        return result

    except Exception as e:
        # Always return a list, even on error
        print(f"Error getting organisations with details: {str(e)}")
        return []

def capability_expiry_datetime(timestamp: Any) -> Optional[datetime]:
    """Convert a capability expiry timestamp (in nanoseconds) into an aware datetime."""
    try:
        value = int(timestamp)
    except (TypeError, ValueError):
        return None
    try:
        return datetime.fromtimestamp(value / 1e9, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None


def parse_capability_timestamp(timestamp):
    """Convert capability timestamp to human-readable format."""
    dt = capability_expiry_datetime(timestamp)
    if not dt:
        return "Unknown"
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def capability_expires_within(timestamp: Any, window: timedelta = timedelta(days=2)) -> bool:
    """Return True when the capability expires within the provided time window."""
    dt = capability_expiry_datetime(timestamp)
    if not dt:
        return False
    now = datetime.now(timezone.utc)
    return dt <= now + window
