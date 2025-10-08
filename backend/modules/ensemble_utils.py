"""Utility helpers for working with ensemble templates and metadata."""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import jinja2

from .logging_config import get_logger

logger = get_logger(__name__)

_DEFAULT_ENSEMBLES_DIR = Path.home() / "ensembles"
_DEFAULT_DEPLOYMENTS_DIR = Path.home() / "nunet" / "nunet" / "deployments"
_METADATA_REQUIRED_FIELDS = ("name", "description", "fields")
_JINJA_ENV = jinja2.Environment(undefined=jinja2.StrictUndefined, autoescape=False)
_ANSI_ESCAPE_RE = re.compile(r"\x1B\[[0-9;]*m")


def _as_path(value: Any) -> Path:
    return value if isinstance(value, Path) else Path(str(value)).expanduser()


def is_resource_field(field_name: str) -> bool:
    """Return True when *field_name* looks like an allocation resource field."""
    return field_name.startswith("allocations_") and "_resources_" in field_name


def get_field_category(field_name: str, field_config: Dict[str, Any]) -> str:
    """Determine a UI category for the given field based on config or naming."""
    category = field_config.get("category")
    if category:
        return str(category)
    if is_resource_field(field_name):
        return "resources"
    return "general"


def parse_hierarchical_field_name(field_name: str) -> Dict[str, Optional[str]]:
    """Extract allocation/resource information from hierarchical field names."""
    parts = field_name.split("_")
    result: Dict[str, Optional[str]] = {
        "allocation_id": None,
        "resource_type": None,
        "resource_property": None,
        "is_resource": False,
    }

    if len(parts) >= 4 and parts[0] == "allocations":
        result["allocation_id"] = parts[1]
        if parts[2] == "resources":
            result["is_resource"] = True
            result["resource_type"] = parts[3]
            if len(parts) > 4:
                result["resource_property"] = "_".join(parts[4:])

    return result


def generate_categorized_fields(metadata: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    """Group metadata fields by category for UI rendering."""
    fields = metadata.get("fields")
    if not isinstance(fields, dict):
        return {}

    categories: Dict[str, List[Dict[str, Any]]] = {}
    for field_name, field_config in fields.items():
        category = get_field_category(field_name, field_config)
        categories.setdefault(category, []).append(
            {
                "name": field_name,
                "config": field_config,
                "hierarchical": parse_hierarchical_field_name(field_name),
            }
        )

    return categories


def generate_form_html(metadata: Dict[str, Any]) -> str:
    """Produce a simple HTML representation for a metadata form."""
    categories = generate_categorized_fields(metadata)
    html_parts: List[str] = []

    if "general" in categories:
        html_parts.append('<div class="form-section">')
        html_parts.append('<h5>General Configuration</h5>')
        for field_info in categories["general"]:
            html_parts.append(generate_field_html(field_info))
        html_parts.append("</div>")

    if "resources" in categories:
        html_parts.append('<div class="form-section">')
        html_parts.append('<div class="resource-section">')
        html_parts.append('<h5 class="resource-header" onclick="toggleResourceSection()">')
        html_parts.append('<i class="bi bi-chevron-down" id="resourceChevron"></i>')
        html_parts.append("Resource Configuration")
        html_parts.append("</h5>")
        html_parts.append('<div class="resource-fields" id="resourceFields">')
        for field_info in categories["resources"]:
            html_parts.append(generate_field_html(field_info))
        html_parts.append("</div>")
        html_parts.append("</div>")
        html_parts.append("</div>")

    return "\n".join(html_parts)


def generate_field_html(field_info: Dict[str, Any]) -> str:
    """Render a single metadata field as HTML."""
    field_name = field_info["name"]
    config = field_info["config"]
    field_type = config.get("type", "text")

    html_parts = [f'<div class="form-field">']
    html_parts.append(
        f'<label for="{field_name}" class="form-label">{config.get("label", field_name)}</label>'
    )

    if field_type == "text":
        attrs = {
            "type": "text",
            "class": "form-control",
            "id": field_name,
            "name": field_name,
            "placeholder": config.get("placeholder"),
            "value": config.get("default"),
        }
        html_parts.append(_render_input(attrs))

    elif field_type == "number":
        attrs = {
            "type": "number",
            "class": "form-control",
            "id": field_name,
            "name": field_name,
            "min": config.get("min"),
            "max": config.get("max"),
            "step": config.get("step"),
            "value": config.get("default"),
        }
        html_parts.append(_render_input(attrs))

    elif field_type == "select":
        html_parts.append(f'<select class="form-control" id="{field_name}" name="{field_name}">')
        default_value = config.get("default")
        for option in config.get("options", []):
            value = option.get("value", "")
            label = option.get("label", value)
            selected = " selected" if value == default_value else ""
            html_parts.append(f'<option value="{value}"{selected}>{label}</option>')
        html_parts.append("</select>")

    elif field_type == "textarea":
        default = config.get("default", "")
        html_parts.append(
            f'<textarea class="form-control" id="{field_name}" name="{field_name}" rows="3">{default}</textarea>'
        )

    if config.get("description"):
        html_parts.append(f'<div class="form-text">{config["description"]}</div>')

    html_parts.append("</div>")
    return "\n".join(html_parts)


def _render_input(attributes: Dict[str, Any]) -> str:
    parts = [f'{key}="{value}"' for key, value in attributes.items() if value is not None]
    return "<input " + " ".join(parts) + ">"


def scan_ensembles_directory(base_path: Optional[Any] = None) -> Dict[str, List[Dict[str, Any]]]:
    """Scan the ensembles folder and group templates by category directory."""
    base_dir = _as_path(base_path or _DEFAULT_ENSEMBLES_DIR)
    if not base_dir.exists():
        logger.warning("Ensembles directory does not exist", extra={"path": str(base_dir)})
        return {}

    categories: Dict[str, List[Dict[str, Any]]] = {}
    for category_dir in sorted(p for p in base_dir.iterdir() if p.is_dir()):
        ensembles: List[Dict[str, Any]] = []
        for yaml_file in sorted(category_dir.glob("*.y*ml")):
            ensemble_info: Dict[str, Any] = {
                "name": yaml_file.stem,
                "path": str(yaml_file),
                "category": category_dir.name,
                "filename": yaml_file.name,
            }

            metadata_path = yaml_file.with_suffix(".json")
            if metadata_path.exists():
                metadata = _load_metadata(metadata_path)
                if metadata:
                    ensemble_info["metadata"] = metadata
                    field_categories: Dict[str, List[str]] = {}
                    for fname, fcfg in metadata.get("fields", {}).items():
                        category = get_field_category(fname, fcfg)
                        field_categories.setdefault(category, []).append(fname)
                    ensemble_info["field_categories"] = field_categories

            ensembles.append(ensemble_info)

        if ensembles:
            categories[category_dir.name] = ensembles

    return categories


def _load_metadata(path: Path) -> Optional[Dict[str, Any]]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            metadata = json.load(handle)
    except Exception as exc:
        logger.warning("Failed to load metadata", extra={"path": str(path), "error": str(exc)})
        return None

    for field in _METADATA_REQUIRED_FIELDS:
        if field not in metadata:
            logger.warning(
                "Metadata missing required field",
                extra={"path": str(path), "missing_field": field},
            )
            return None

    return metadata


def load_ensemble_metadata(ensemble_path: str | Path) -> Optional[Dict[str, Any]]:
    """Load JSON metadata that accompanies an ensemble template."""
    metadata_path = _as_path(ensemble_path).with_suffix(".json")
    if not metadata_path.exists():
        logger.info("No metadata file found", extra={"ensemble": str(ensemble_path)})
        return None
    return _load_metadata(metadata_path)


def process_yaml_template(
    yaml_path: str | Path,
    form_values: Dict[str, Any],
    deployment_type: str = "local",
) -> Optional[str]:
    """Render a YAML template with the provided values using Jinja2."""
    path = _as_path(yaml_path)
    try:
        template_source = path.read_text(encoding="utf-8")
    except Exception as exc:
        logger.error("Failed to read YAML template", extra={"path": str(path), "error": str(exc)})
        return None

    values = dict(form_values)
    if deployment_type == "non_targeted":
        values.pop("peer_id", None)

    try:
        template = _JINJA_ENV.from_string(template_source)
        rendered = template.render(**values)
    except jinja2.UndefinedError as exc:
        logger.error("Template rendering missing value", extra={"error": str(exc)})
        return None
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("Error processing YAML template", extra={"path": str(path), "error": str(exc)})
        return None

    if deployment_type == "non_targeted":
        rendered = _strip_peer_lines(rendered)

    return rendered


def _strip_peer_lines(rendered: str) -> str:
    cleaned = re.sub(r"^\s*peer:\s*.*$", "", rendered, flags=re.MULTILINE)
    # Collapse accidental double newlines resulting from removal
    return re.sub(r"\n{3,}", "\n\n", cleaned)


def generate_timestamped_filename(original_name: str) -> str:
    """Return a timestamped filename for storing rendered deployments."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{original_name}_{timestamp}.yaml"


def validate_form_data(metadata: Dict[str, Any], form_values: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """Validate *form_values* against metadata constraints."""
    fields = metadata.get("fields")
    if not isinstance(fields, dict):
        return False, ["No field definitions found in metadata"]

    errors: List[str] = []

    for field_name, field_config in fields.items():
        if field_config.get("required"):
            value = form_values.get(field_name)
            if _is_blank(value):
                errors.append(f"Field '{field_name}' is required")

    for field_name, field_value in form_values.items():
        if field_name not in fields:
            continue
        config = fields[field_name]
        field_type = config.get("type", "text")

        if field_type == "number" and not _is_blank(field_value):
            number = _coerce_number(field_name, field_value, config, errors)
            if number is None:
                continue
            _check_bounds(field_name, number, config, errors)

        pattern = config.get("pattern")
        if pattern and not _is_blank(field_value):
            if not re.match(pattern, str(field_value)):
                errors.append(f"Field '{field_name}' does not match required format")

        if field_type == "select" and not _is_blank(field_value):
            valid_options = [opt.get("value") for opt in config.get("options", [])]
            if field_value not in valid_options:
                errors.append(f"Field '{field_name}' must be one of {valid_options}")

    return not errors, errors


def _is_blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and value.strip() == "":
        return True
    return False


def _coerce_number(field_name: str, value: Any, config: Dict[str, Any], errors: List[str]) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        errors.append(f"Field '{field_name}' must be a number")
        return None


def _check_bounds(field_name: str, value: float, config: Dict[str, Any], errors: List[str]) -> None:
    if "min" in config and value < config["min"]:
        errors.append(f"Field '{field_name}' must be at least {config['min']}")
    if "max" in config and value > config["max"]:
        errors.append(f"Field '{field_name}' must be at most {config['max']}")


def save_deployment_instance(
    template_path: str | Path,
    processed_content: str,
    timestamp: Optional[str] = None,
    deployments_dir: Optional[Any] = None,
) -> Optional[str]:
    """Persist rendered YAML to the deployments directory."""
    if not processed_content:
        return None

    deployments_path = _as_path(deployments_dir or _DEFAULT_DEPLOYMENTS_DIR)
    deployments_path.mkdir(parents=True, exist_ok=True)

    original_name = _as_path(template_path).stem
    timestamp = timestamp or datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{original_name}_{timestamp}.yaml"
    output_path = deployments_path / filename

    try:
        output_path.write_text(processed_content, encoding="utf-8")
        logger.info("Saved deployment instance", extra={"path": str(output_path)})
        return str(output_path)
    except Exception as exc:
        logger.error("Error saving deployment instance", extra={"error": str(exc)})
        return None


def get_ensemble_categories() -> List[str]:
    """Return available ensemble categories."""
    return list(scan_ensembles_directory().keys())


def get_ensembles_by_category(category: str) -> List[Dict[str, Any]]:
    """Return ensemble metadata for a single category."""
    return scan_ensembles_directory().get(category, [])


def get_local_peer_id(dms_manager: Optional[Any] = None) -> Optional[str]:
    """Return the local peer id from the DMS manager if available."""
    try:
        if dms_manager is None:
            from modules.dms_manager import DMSManager  # local import to avoid cycles

            dms_manager = DMSManager()

        peer_info = dms_manager.get_self_peer_info() or {}
        return peer_info.get("peer_id")
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("Error getting local peer ID", extra={"error": str(exc)})
        return None


def _parse_peer_message(message: str) -> List[Dict[str, str]]:
    cleaned = _ANSI_ESCAPE_RE.sub("", message)
    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        logger.error("Peer JSON parse error", extra={"error": str(exc)})
        return []

    peers: Iterable[Any] = payload.get("Peers", [])
    results: List[Dict[str, str]] = []
    for peer in peers:
        if isinstance(peer, dict):
            results.append(
                {
                    "id": peer.get("ID", ""),
                    "name": peer.get("Name", peer.get("ID", "Unknown")),
                }
            )
        elif isinstance(peer, str):
            results.append({"id": peer, "name": peer})
    return results


def get_known_peers(dms_manager: Optional[Any] = None) -> List[Dict[str, str]]:
    """Return known peers from DMS."""
    try:
        if dms_manager is None:
            from modules.dms_manager import DMSManager  # local import to avoid cycles

            dms_manager = DMSManager()

        peers_json = dms_manager.view_peer_details()
        if peers_json.get("status") != "success":
            return []
        message = peers_json.get("message", "")
        return _parse_peer_message(message)
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("Error getting known peers", extra={"error": str(exc)})
        return []


def get_deployment_options(dms_manager: Optional[Any] = None) -> Dict[str, Any]:
    """Return form helper options for deployments (peer list, types)."""
    return {
        "local_peer_id": get_local_peer_id(dms_manager),
        "known_peers": get_known_peers(dms_manager),
        "deployment_types": [
            {
                "value": "local",
                "label": "Deploy Locally",
                "description": "Deploy to this appliance",
            },
            {
                "value": "targeted",
                "label": "Targeted Deployment",
                "description": "Deploy to a specific peer",
            },
            {
                "value": "non_targeted",
                "label": "Non-Targeted Deployment",
                "description": "Let the network decide",
            },
        ],
    }


__all__ = [
    "generate_categorized_fields",
    "generate_field_html",
    "generate_form_html",
    "generate_timestamped_filename",
    "get_deployment_options",
    "get_ensemble_categories",
    "get_ensembles_by_category",
    "get_known_peers",
    "get_local_peer_id",
    "is_resource_field",
    "load_ensemble_metadata",
    "parse_hierarchical_field_name",
    "process_yaml_template",
    "save_deployment_instance",
    "scan_ensembles_directory",
    "validate_form_data",
]

