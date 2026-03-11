"""
Contract template discovery and retrieval utilities.

- Local templates live under ``backend/contracts`` and are treated similarly to ensemble
  templates (one file per template).
- Per-organisation templates can be fetched from the ``contracts_url`` declared in
  ``known_orgs/known_organizations.json`` when present.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

try:
    import requests
except ImportError:  # pragma: no cover - optional dependency in some environments
    requests = None  # type: ignore[assignment]

from .path_constants import CONTRACTS_DIR, HOME_DIR
from .org_utils import load_known_organizations

logger = logging.getLogger(__name__)


class ContractTemplate(Dict[str, Any]):
    """TypedDict-like alias for readability."""


def _clean_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _clean_list(values: Any) -> List[str]:
    if not isinstance(values, Iterable) or isinstance(values, (str, bytes)):
        return []
    cleaned: List[str] = []
    for item in values:
        text = _clean_str(item)
        if text:
            cleaned.append(text)
    return cleaned


def _load_json_file(path: Path) -> Optional[Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError:
        return None
    except json.JSONDecodeError as exc:
        logger.warning("Invalid JSON in contract template %s: %s", path, exc)
        return None
    except Exception as exc:
        logger.warning("Failed to read contract template %s: %s", path, exc)
        return None


def _normalise_template_payload(
    *,
    template_id: str,
    source: str,
    organization_did: Optional[str],
    origin: str,
    payload: Dict[str, Any],
) -> Optional[ContractTemplate]:
    contract_block = payload.get("contract")
    if not isinstance(contract_block, dict):
        logger.warning("Skipping contract template %s (%s) because 'contract' section is missing", template_id, origin)
        return None

    name = _clean_str(payload.get("name")) or template_id
    description = _clean_str(payload.get("description"))
    tags = _clean_list(payload.get("tags"))
    categories = _clean_list(payload.get("categories"))
    organizations = _clean_list(payload.get("organizations"))
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else None
    default_destination = _clean_str(payload.get("default_destination"))

    template: ContractTemplate = {
        "template_id": template_id,
        "display_name": name,
        "description": description,
        "tags": tags,
        "categories": categories,
        "contract": contract_block,
        "source": source,
        "origin": origin,
        "organization_did": organization_did,
        "organizations": organizations,
    }
    if default_destination:
        template["default_destination"] = default_destination
    if metadata:
        template["metadata"] = metadata
    return template


def _gather_local_templates() -> List[ContractTemplate]:
    templates: List[ContractTemplate] = []
    base_dir = CONTRACTS_DIR
    if not base_dir.exists():
        try:
            base_dir.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            logger.debug("Unable to create contract templates directory %s: %s", base_dir, exc)
            return templates

    for item in sorted(base_dir.glob("*.json")):
        payload = _load_json_file(item)
        if not isinstance(payload, dict):
            continue
        template_id = f"local:{item.stem}"
        template = _normalise_template_payload(
            template_id=template_id,
            source="local",
            organization_did=None,
            origin=str(item.relative_to(HOME_DIR)),
            payload=payload,
        )
        if template:
            template["filename"] = item.name
            templates.append(template)
    return templates


def _contracts_url_for_org(org_did: str) -> Optional[str]:
    known = load_known_organizations()
    entry = known.get(org_did)
    if isinstance(entry, dict):
        url = entry.get("contracts_url") or entry.get("contractsUrl")
        return _clean_str(url)
    return None


def _fetch_remote_templates(org_did: str, url: str, *, timeout: int = 10) -> List[ContractTemplate]:
    templates: List[ContractTemplate] = []
    if requests is None:
        logger.warning("Cannot fetch remote contract templates for %s: requests library not available", org_did)
        return templates
    try:
        response = requests.get(url, timeout=timeout)
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        logger.warning("Failed to fetch contract templates for %s from %s: %s", org_did, url, exc)
        return templates

    if isinstance(payload, dict):
        iterator = payload.items()
    elif isinstance(payload, list):
        iterator = ((str(idx), entry) for idx, entry in enumerate(payload))
    else:
        logger.warning("Unexpected contract template payload type %s from %s", type(payload).__name__, url)
        return templates

    for key, entry in iterator:
        if not isinstance(entry, dict):
            continue
        template_id = f"remote:{org_did}:{key}"
        template = _normalise_template_payload(
            template_id=template_id,
            source="remote",
            organization_did=org_did,
            origin=url,
            payload=entry,
        )
        if template:
            templates.append(template)
    return templates


def list_contract_templates(*, org_did: Optional[str] = None, timeout: int = 10) -> List[ContractTemplate]:
    """
    Return contract templates available to the appliance.
    When org_did is provided, templates associated with that organisation (via contracts_url)
    are fetched and included.
    """
    templates = _gather_local_templates()

    if org_did:
        url = _contracts_url_for_org(org_did)
        if url:
            templates.extend(_fetch_remote_templates(org_did, url, timeout=timeout))

    if org_did:
        org_lower = org_did.lower()
        filtered: List[ContractTemplate] = []
        for template in templates:
            orgs = template.get("organizations") or []
            if not orgs or org_lower in {org.lower() for org in orgs} or template.get("organization_did"):
                # include when template explicitly matches org or is remote for this org, or has no restrictions
                filtered.append(template)
        templates = filtered

    templates.sort(key=lambda tpl: (tpl.get("organization_did") or "", tpl.get("display_name") or tpl["template_id"]))
    return templates


def get_contract_template(template_id: str, *, org_did: Optional[str] = None, timeout: int = 10) -> Optional[ContractTemplate]:
    """
    Retrieve a single contract template by identifier.
    """
    templates = list_contract_templates(org_did=org_did, timeout=timeout)
    for template in templates:
        if template.get("template_id") == template_id:
            return template
    return None


__all__ = [
    "ContractTemplate",
    "get_contract_template",
    "list_contract_templates",
]
