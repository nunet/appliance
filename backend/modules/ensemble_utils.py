"""
Utility helpers for FastAPI ensemble endpoints.

The legacy menu-specific helpers have been removed.  Only the functions that
back the current API surface remain.
"""

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import jinja2

from .dms_manager import DMSManager
from .path_constants import APPLIANCE_DEPLOYMENTS_DIR, ENSEMBLES_SCAN_ROOT

logger = logging.getLogger(__name__)

ENSEMBLE_ROOT = ENSEMBLES_SCAN_ROOT
DEPLOYMENTS_DIR = APPLIANCE_DEPLOYMENTS_DIR
_ANSI_RE = re.compile(r"\x1B\[[0-9;]*m")


# --------------------------------------------------------------------------- #
# Template discovery & metadata
# --------------------------------------------------------------------------- #

def scan_ensembles_directory(base_path: Optional[str | Path] = None) -> Dict[str, List[Dict[str, Any]]]:
    """
    Recursively scan the ensembles directory and return a mapping of category -> templates.
    Each template entry contains name, filename, full path, and optional metadata.
    """
    root = Path(base_path).expanduser() if base_path else ENSEMBLE_ROOT
    if not root.exists():
        logger.debug("Ensemble directory does not exist: %s", root)
        return {}

    categories: Dict[str, List[Dict[str, Any]]] = {}
    for entry in sorted(root.iterdir()):
        if not entry.is_dir():
            continue
        templates: List[Dict[str, Any]] = []
        for tpl in sorted(list(entry.glob("*.yaml")) + list(entry.glob("*.yml"))):
            info: Dict[str, Any] = {
                "name": tpl.stem,
                "filename": tpl.name,
                "path": str(tpl),
                "category": entry.name,
            }
            metadata = load_ensemble_metadata(str(tpl))
            if metadata:
                info["metadata"] = metadata
            templates.append(info)
        if templates:
            categories[entry.name] = templates
    return categories


def load_ensemble_metadata(ensemble_path: str) -> Optional[Dict[str, Any]]:
    """Load JSON metadata that sits alongside a YAML template."""
    metadata_path = Path(ensemble_path).with_suffix(".json")
    if not metadata_path.exists():
        return None
    try:
        data = json.loads(metadata_path.read_text())
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Failed to read metadata %s: %s", metadata_path, exc)
        return None

    required = {"name", "description", "fields"}
    if not required.issubset(data):
        logger.warning("Metadata %s is missing required keys: %s", metadata_path, required - set(data))
        return None
    return data


# --------------------------------------------------------------------------- #
# Template rendering & validation
# --------------------------------------------------------------------------- #

def process_yaml_template(
    yaml_path: str,
    form_values: Dict[str, Any],
    deployment_type: str = "local",
) -> Optional[str]:
    """Render a YAML template with the provided form values."""
    try:
        template_text = Path(yaml_path).read_text()
    except Exception as exc:
        logger.error("Unable to read template %s: %s", yaml_path, exc)
        return None

    values = dict(form_values or {})
    if deployment_type == "non_targeted" and not values.get("peer_id"):
        # Provide a dummy peer_id to satisfy templates using StrictUndefined.
        # Will be removed from the rendered YAML below.
        values["peer_id"] = "__DUMMY_PEER__"

    try:
        template = jinja2.Environment(undefined=jinja2.StrictUndefined).from_string(template_text)
        rendered = template.render(**values)
    except jinja2.exceptions.UndefinedError as exc:
        logger.error("Missing value rendering %s: %s", yaml_path, exc)
        return None
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("Failed to render %s: %s", yaml_path, exc)
        return None

    # Post-render mutation of 'peer' based on deployment type.
    # Prefer YAML-aware mutation; fallback to regex if YAML parsing is unavailable or fails.
    try:
        import yaml  # type: ignore
        use_yaml = True
    except Exception:
        use_yaml = False

    if use_yaml:
        try:
            # Single-document YAML expected
            doc = yaml.safe_load(rendered)

            if isinstance(doc, dict):
                nodes = doc.get("nodes")
                target_peer = values.get("peer_id")

                if isinstance(nodes, dict):
                    for node in nodes.values():
                        if isinstance(node, dict):
                            if deployment_type == "non_targeted":
                                node.pop("peer", None)
                            elif deployment_type in ("local", "targeted") and target_peer:
                                node["peer"] = target_peer

                elif isinstance(nodes, list):
                    for node in nodes:
                        if isinstance(node, dict):
                            if deployment_type == "non_targeted":
                                node.pop("peer", None)
                            elif deployment_type in ("local", "targeted") and target_peer:
                                node["peer"] = target_peer

            rendered = yaml.safe_dump(doc, sort_keys=False).strip() + "\n"

        except Exception as exc:
            logger.warning(
                "YAML post-processing failed for %s (%s); falling back to regex: %s",
                yaml_path, deployment_type, exc
            )
            if deployment_type == "non_targeted":
                rendered = re.sub(r"^\s*peer:\s*.*?$", "", rendered, flags=re.MULTILINE)
                rendered = re.sub(r"\n{3,}", "\n\n", rendered)
            elif deployment_type in ("local", "targeted"):
                peer = values.get("peer_id")
                if peer:
                    rendered = re.sub(r"^(\s*)peer:\s*.*?$", rf"\1peer: {peer}", rendered, flags=re.MULTILINE)
    else:
        if deployment_type == "non_targeted":
            rendered = re.sub(r"^\s*peer:\s*.*?$", "", rendered, flags=re.MULTILINE)
            rendered = re.sub(r"\n{3,}", "\n\n", rendered)
        elif deployment_type in ("local", "targeted"):
            peer = values.get("peer_id")
            if peer:
                rendered = re.sub(r"^(\s*)peer:\s*.*?$", rf"\1peer: {peer}", rendered, flags=re.MULTILINE)

    return rendered


def validate_form_data(metadata: Dict[str, Any], form_values: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """Validate user-provided form data against metadata definitions."""
    if "fields" not in metadata:
        return False, ["No field definitions found in metadata."]

    errors: List[str] = []
    fields: Dict[str, Any] = metadata["fields"]

    # Required fields
    for field_name, field_cfg in fields.items():
        if field_cfg.get("required") and not form_values.get(field_name):
            errors.append(f"Field '{field_name}' is required.")

    # Type & constraint checks
    for field_name, raw_value in form_values.items():
        if field_name not in fields:
            continue
        if raw_value in (None, "", []):
            continue  # allow empty optional fields

        cfg = fields[field_name]
        field_type = cfg.get("type", "text")

        try:
            if field_type == "number":
                value = float(raw_value)
            elif field_type == "integer":
                value = int(raw_value)
            else:
                value = raw_value
        except (TypeError, ValueError):
            errors.append(f"Field '{field_name}' must be a valid {field_type}.")
            continue

        pattern = cfg.get("pattern")
        if pattern and not re.fullmatch(pattern, str(raw_value)):
            errors.append(f"Field '{field_name}' does not match the required pattern.")

        if field_type in {"number", "integer"}:
            minimum = cfg.get("min")
            maximum = cfg.get("max")
            if minimum is not None and value < minimum:
                errors.append(f"Field '{field_name}' must be at least {minimum}.")
            if maximum is not None and value > maximum:
                errors.append(f"Field '{field_name}' must be at most {maximum}.")

    return (len(errors) == 0, errors)


# --------------------------------------------------------------------------- #
# Deployment helpers
# --------------------------------------------------------------------------- #

def save_deployment_instance(template_path: str, processed_content: str, timestamp: str) -> Optional[str]:
    """Persist a rendered ensemble file under the appliance deployments directory."""
    try:
        DEPLOYMENTS_DIR.mkdir(parents=True, exist_ok=True)
        name = Path(template_path).stem
        destination = DEPLOYMENTS_DIR / f"{name}_{timestamp}.yaml"
        destination.write_text(processed_content)
        logger.debug("Saved rendered ensemble to %s", destination)
        return str(destination)
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("Failed to save deployment instance: %s", exc)
        return None


def get_local_peer_id(dms_manager: Optional[DMSManager] = None) -> Optional[str]:
    mgr = dms_manager or DMSManager()
    try:
        info = mgr.get_self_peer_info()
        if isinstance(info, dict):
            return info.get("peer_id")
        return None
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("Failed to obtain local peer id: %s", exc)
        return None


def get_known_peers(dms_manager: Optional[DMSManager] = None) -> List[Dict[str, str]]:
    mgr = dms_manager or DMSManager()
    try:
        result = mgr.view_peer_details()
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("Failed to obtain peer list: %s", exc)
        return []

    if result.get("status") != "success":
        return []

    payload = result.get("message") or ""
    clean = _ANSI_RE.sub("", payload)
    peers: List[Dict[str, str]] = []

    try:
        data = json.loads(clean)
    except json.JSONDecodeError:
        data = None

    iterable = []
    if isinstance(data, dict):
        iterable = data.get("Peers") or data.get("peers") or []
    elif isinstance(data, list):
        iterable = data
    else:
        iterable = []

    for entry in iterable:
        if isinstance(entry, dict):
            peer_id = entry.get("ID") or entry.get("id") or ""
            name = entry.get("Name") or entry.get("ID") or peer_id
            peers.append({"id": str(peer_id), "name": str(name)})
        elif isinstance(entry, str):
            peers.append({"id": entry, "name": entry})

    return peers


def get_deployment_options(dms_manager: Optional[DMSManager] = None) -> Dict[str, Any]:
    """Return the peer/deployment options used by the UI forms."""
    return {
        "local_peer_id": get_local_peer_id(dms_manager),
        "known_peers": get_known_peers(dms_manager),
        "deployment_types": [
            {"value": "local", "label": "Deploy Locally", "description": "Deploy to this appliance"},
            {"value": "targeted", "label": "Targeted Deployment", "description": "Deploy to a specific peer"},
            {"value": "non_targeted", "label": "Non-Targeted Deployment", "description": "Let the network decide"},
        ],
    }


# --------------------------------------------------------------------------- #
# Misc helpers
# --------------------------------------------------------------------------- #

def generate_timestamped_filename(original_name: str) -> str:
    """Create a timestamped filename for a rendered deployment."""
    return f"{original_name}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.yaml"
