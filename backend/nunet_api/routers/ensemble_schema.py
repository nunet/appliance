# backend/nunet_api/routers/ensemble_schema.py
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel

from modules.ensemble_manager_v2 import EnsembleManagerV2
from modules.path_constants import (
    DEFAULT_CONTRACT_JSON_TEMPLATE,
    DEFAULT_ENSEMBLE_JSON_TEMPLATE,
)

from ..schemas import (
    UploadTemplateResponse,
    SimpleStatusResponse,
    FormSchema,
    FormField,
    FormFieldOption,
    SchemaHints,
    SchemaFieldOverride,
)

router = APIRouter()

# ---------- Helpers ----------
def _mgr() -> EnsembleManagerV2:
    return EnsembleManagerV2()

def _base_dir() -> Path:
    return _mgr().base_dir.resolve()

_VAR_RE = re.compile(r"{{\s*([A-Za-z0-9_]+)\s*}}")

def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def _titleize(s: str) -> str:
    return re.sub(r"[_\-\s]+", " ", s).strip().title()

def _sanitize_filename(name: str, allowed_suffixes=(".yaml", ".yml", ".json")) -> str:
    name = name.replace("\\", "/").split("/")[-1]
    if not any(name.endswith(suf) for suf in allowed_suffixes):
        raise HTTPException(status_code=400, detail="Unsupported file extension")
    if not re.match(r"^[A-Za-z0-9._\-]+$", name):
        raise HTTPException(status_code=400, detail="Filename contains invalid characters")
    return name

def _ensure_inside_base(p: Path) -> Path:
    p = p.resolve()
    base = _base_dir()
    if not str(p).startswith(str(base)):
        raise HTTPException(status_code=400, detail="Path must be inside ~/ensembles")
    return p

def _resolve_template_path(template_path: str) -> Path:
    if not template_path:
        raise HTTPException(status_code=400, detail="template_path is required")
    rel = template_path.strip().lstrip("/\\")
    candidate = _base_dir() / Path(rel)
    return _ensure_inside_base(candidate)

def _vars_from_text(yaml_text: str) -> List[str]:
    return sorted(set(_VAR_RE.findall(yaml_text)))

def _infer_field(name: str, override: Optional[SchemaFieldOverride]) -> FormField:
    lower = name.lower()
    f = FormField(label=_titleize(name), type="text", required=True)

    # Heuristics kept minimal and predictable
    if "port" in lower:
        f.type, f.min, f.max = "number", 1024, 65535
        f.description = "Port number"
        f.category = f.category or "network"
    elif lower.endswith("_cores") or "cores" in lower:
        f.type, f.step, f.default = "number", 0.5, 0.5
        f.description = "Number of CPU cores"
        f.category = f.category or "resources"
    elif "ram" in lower or "memory" in lower:
        f.type, f.step = "number", 0.5
        f.description = "RAM size (GiB)"
        f.category = f.category or "resources"
    elif "disk" in lower or "storage" in lower:
        f.type, f.step = "number", 0.5
        f.description = "Disk size (GiB)"
        f.category = f.category or "resources"
    elif lower in ("dns_name",) or "dns" in lower or "host" in lower or "domain" in lower:
        f.type = "text"
        f.placeholder = "my-service"
        f.pattern = r"^[a-z0-9-]+$"
        f.description = "DNS-safe name (lowercase letters, numbers, hyphens)"
        f.category = f.category or "network"
    elif lower == "peer_id":
        f.type = "text"
        f.required = True
        f.placeholder = "12D3KooW..."
        f.description = "Target peer ID for deployment"
        f.category = f.category or "targeting"

    # Apply override (if provided)
    if override:
        if override.type:
            f.type = override.type
        if override.options is not None:
            f.options = override.options
        for attr in ("default", "min", "max", "step", "required",
                     "placeholder", "description", "category", "pattern"):
            val = getattr(override, attr)
            if val is not None:
                setattr(f, attr, val)

    return f

def _to_jsonable(obj: Any) -> Any:
    """Return a plain JSON-serialisable structure from Pydantic v1/v2 models, dicts, lists, etc."""
    # Pydantic v2
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    # Pydantic v1
    if hasattr(obj, "dict"):
        return obj.dict()
    # Collections
    if isinstance(obj, list):
        return [_to_jsonable(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _to_jsonable(v) for k, v in obj.items()}
    return obj

def _build_schema(yaml_path: Path, yaml_text: str, hints: Optional[SchemaHints]) -> Tuple[FormSchema, List[str], Dict[str, Any]]:
    variables = _vars_from_text(yaml_text)
    name = hints.name if hints and hints.name else _titleize(yaml_path.stem)
    desc = hints.description if hints else None
    overrides = (hints.field_overrides if hints else {}) or {}

    fields: Dict[str, FormField] = {}
    for v in variables:
        fields[v] = _infer_field(v, overrides.get(v))

    schema = FormSchema(name=name, description=desc, fields=fields)

    needs_peer = "peer_id" in variables
    supports = ["local", "targeted", "non_targeted"] if needs_peer else ["non_targeted"]

    meta = {
        "yaml_sha256": _sha256_bytes(yaml_text.encode("utf-8")),
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "supports": supports,
        "needs_peer_id": needs_peer,
    }

    warnings: List[str] = []
    if not variables:
        warnings.append("No user inputs detected in template")

    return schema, warnings, meta

def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    plain = _to_jsonable(data)
    path.write_text(json.dumps(plain, indent=2), encoding="utf-8")

def _category_for(file_path: Path, root: Path) -> str:
    """
    Category = first directory under root; files directly under root -> 'root'
    """
    try:
        rel = file_path.relative_to(root)
    except Exception:
        return "root"
    parts = rel.parts
    if len(parts) >= 2:
        return parts[0]  # top-level folder under root
    return "root"

def _relpath(file_path: Path, root: Path) -> str:
    try:
        return str(file_path.relative_to(root))
    except Exception:
        return str(file_path)

def _matching_yaml_for(json_path: Path) -> Path | None:
    """
    Find YAML with same stem in the same directory (stem.yaml or stem.yml).
    """
    cand1 = json_path.with_suffix(".yaml")
    cand2 = json_path.with_suffix(".yml")
    if cand1.exists():
        return cand1
    if cand2.exists():
        return cand2
    return None

class TemplateDetailResponse(BaseModel):
    status: str = "success"
    yaml_path: str
    json_path: Optional[str] = None
    category: str
    yaml_content: str
    json_content: Optional[str] = None
    modified_at: Optional[str] = None
    size: Optional[int] = None

class UpdateTemplatePayload(BaseModel):
    template_path: str
    yaml_content: str
    json_content: Optional[str] = None

def _load_default_form(contract_required: bool) -> Dict[str, Any]:
    """
    Load the bundled default JSON form used when the user does not upload one.
    """
    template_path = (
        DEFAULT_CONTRACT_JSON_TEMPLATE if contract_required else DEFAULT_ENSEMBLE_JSON_TEMPLATE
    )
    if not template_path.exists():
        raise HTTPException(
            status_code=500,
            detail=f"Default form template missing: {template_path}",
        )
    try:
        with open(template_path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except Exception as exc:  # noqa: BLE001 - surface specific parsing failure
        raise HTTPException(
            status_code=500,
            detail=f"Unable to load default form template: {exc}",
        ) from exc


# ---------- Endpoints ----------

@router.post("/templates/upload", response_model=UploadTemplateResponse, status_code=201)
async def upload_template_simple(
    # required YAML
    file: UploadFile = File(..., description="YAML file (.yaml/.yml)"),
    # optional sidecar JSON (if provided, we just save it with same stem)
    sidecar: Optional[UploadFile] = File(None, description="Optional JSON schema; saved as <yaml-stem>.json"),
    # simple categorization (folder under ~/ensembles)
    category: Optional[str] = Form(None, description="Folder under ~/ensembles to store files"),
    # overwrite confirmation
    confirm_overwrite: bool = Form(False),
    # whether the default JSON form should include contract fields
    contract_required: bool = Form(False, description="Use the contract default form template"),
):
    """
    One-stop simple flow:
    - Upload YAML (+ optional JSON). If JSON is present, we save both together and return.
    - If JSON isn't present we copy one of the bundled default JSON forms (contract/no-contract).
    - If the YAML/JSON already exist and confirm_overwrite is false -> 409 confirm_overwrite.
    """
    base = _base_dir()

    # --- Determine destination paths
    yaml_name = _sanitize_filename(file.filename, allowed_suffixes=(".yaml", ".yml"))
    dest_dir = _ensure_inside_base((base / (category or "")).resolve())
    dest_yaml = _ensure_inside_base(dest_dir / yaml_name)
    dest_json = dest_yaml.with_suffix(".json")  # always keep stem alignment

    # --- Existence checks (both YAML and sidecar path)
    exists_yaml = dest_yaml.exists()
    exists_json = dest_json.exists()
    if (exists_yaml or exists_json) and not confirm_overwrite:
        raise HTTPException(
            status_code=409,
            detail={
                "status": "confirm_overwrite",
                "message": "Template or sidecar already exists. Resend with confirm_overwrite=true to overwrite.",
                "existing_paths": {
                    "yaml": str(dest_yaml.relative_to(base)) if exists_yaml else None,
                    "json": str(dest_json.relative_to(base)) if exists_json else None,
                },
            }
        )

    # --- Save YAML
    data = await file.read()
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_yaml.write_bytes(data)

    # If user provided a sidecar JSON, save it and we're done
    if sidecar:
        content = await sidecar.read()
        # save with YAML stem to keep your listing behavior consistent
        _write_json(dest_json, json.loads(content.decode("utf-8")))
        stat = dest_yaml.stat()
        return UploadTemplateResponse(
            status="success",
            yaml_path=str(dest_yaml.relative_to(base)),
            json_path=str(dest_json.relative_to(base)),
            name=dest_yaml.name,
            size=stat.st_size,
            modified_at=datetime.fromtimestamp(stat.st_mtime).isoformat(),
            message="YAML and JSON saved."
        )

    # --- Default JSON path
    default_schema = _load_default_form(contract_required)
    _write_json(dest_json, default_schema)
    stat = dest_yaml.stat()
    return UploadTemplateResponse(
        status="success",
        yaml_path=str(dest_yaml.relative_to(base)),
        json_path=str(dest_json.relative_to(base)),
        name=dest_yaml.name,
        size=stat.st_size,
        modified_at=datetime.fromtimestamp(stat.st_mtime).isoformat(),
        message="YAML saved and default JSON schema copied."
    )

@router.get("/templates/forms", response_model=dict)
def list_form_templates(
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    page_size: int = Query(10, ge=1, le=100, description="Items per page"),
    include_schema: bool = Query(True, description="Include parsed JSON schema"),
    require_yaml_match: bool = Query(True, description="Only include JSONs that have a matching YAML with same stem"),
):
    """
    List JSON form templates under ~/ensembles, categorized by folder.
    By default, only JSON files that *describe* a YAML (same stem) are returned.
    """
    base = _base_dir()
    json_files = sorted(base.rglob("*.json"))

    items = []
    errors = []

    for jf in json_files:
        yaml_match = _matching_yaml_for(jf)
        if require_yaml_match and yaml_match is None:
            continue

        schema = None
        parse_error = None
        if include_schema:
            try:
                with open(jf, "r", encoding="utf-8") as f:
                    schema = json.load(f)
            except Exception as e:
                parse_error = str(e)

        stat = jf.stat()
        item = {
            "category": _category_for(jf, base),
            "name": jf.name,
            "stem": jf.stem,
            "path": _relpath(jf, base),
            "yaml_path": _relpath(yaml_match, base) if yaml_match else None,
            "title": (schema.get("name") if isinstance(schema, dict) else None) or jf.stem,
            "description": (schema.get("description") if isinstance(schema, dict) else None),
            "size": stat.st_size,
            "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
        }
        if include_schema:
            item["schema"] = schema if parse_error is None else None
            if parse_error:
                item["schema_error"] = parse_error

        items.append(item)

    # Sort by category then name for deterministic output
    items.sort(key=lambda x: (x["category"].lower(), x["name"].lower()))

    total = len(items)
    start = (page - 1) * page_size
    end = start + page_size
    page_items = items[start:end]

    # Build category groups for the *current page*
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for it in page_items:
        groups.setdefault(it["category"], []).append(it)

    # Also include category totals across *all* items
    category_totals: Dict[str, int] = {}
    for it in items:
        category_totals[it["category"]] = category_totals.get(it["category"], 0) + 1

    return {
        "root": str(base),
        "page": page,
        "page_size": page_size,
        "total": total,
        "category_totals": category_totals,
        "groups": groups,      # categorized view for the current page
        "items": page_items,   # flat view for the current page
    }

@router.get("/templates/schema", response_model=FormSchema)
def get_effective_schema(
    template_path: str = Query(..., description="Path under ~/ensembles, e.g. rare-evo/floppybird.yaml"),
    source: str = Query("auto", description="'auto' uses sidecar if present, otherwise inferred")
):
    base = _base_dir()
    yaml_path = _ensure_inside_base((base / template_path).expanduser())
    if not yaml_path.exists():
        raise HTTPException(status_code=404, detail="Template not found")

    sidecar = yaml_path.with_suffix(".json")
    if source in ("auto", "sidecar") and sidecar.exists():
        try:
            data = json.loads(sidecar.read_text(encoding="utf-8"))
            try:
                # Pydantic v2
                return FormSchema.model_validate(data)
            except AttributeError:
                # Pydantic v1 fallback
                return FormSchema.parse_obj(data)

        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Invalid sidecar JSON: {e}")

    # Fallback: infer on-the-fly (no write)
    yaml_text = yaml_path.read_text(encoding="utf-8")
    schema, _, _ = _build_schema(yaml_path, yaml_text, hints=None)
    return schema

@router.get("/templates/detail", response_model=TemplateDetailResponse)
def get_template_detail(
    template_path: str = Query(..., description="Path under ~/ensembles, e.g. demos/floppybird.yaml")
) -> TemplateDetailResponse:
    yaml_path = _resolve_template_path(template_path)
    if not yaml_path.exists():
        raise HTTPException(status_code=404, detail="Template not found")
    base = _base_dir()
    try:
        yaml_text = yaml_path.read_text(encoding="utf-8")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Unable to read YAML file: {exc}") from exc
    json_path = yaml_path.with_suffix(".json")
    json_text = None
    if json_path.exists():
        try:
            json_text = json_path.read_text(encoding="utf-8")
        except Exception:
            json_text = None
    stat = yaml_path.stat()
    try:
        yaml_rel = str(yaml_path.relative_to(base))
    except Exception:
        yaml_rel = str(yaml_path)
    json_rel = None
    if json_path.exists():
        try:
            json_rel = str(json_path.relative_to(base))
        except Exception:
            json_rel = str(json_path)
    return TemplateDetailResponse(
        yaml_path=yaml_rel,
        json_path=json_rel,
        category=_category_for(yaml_path, base),
        yaml_content=yaml_text,
        json_content=json_text,
        modified_at=datetime.fromtimestamp(stat.st_mtime).isoformat(),
        size=stat.st_size,
    )

@router.put("/templates/detail", response_model=UploadTemplateResponse)
def update_template(payload: UpdateTemplatePayload) -> UploadTemplateResponse:
    yaml_path = _resolve_template_path(payload.template_path)
    # Allow creating YAML file if it doesn't exist (for JSON-only templates)
    if not yaml_path.exists():
        # Ensure parent directory exists
        yaml_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        yaml_path.write_text(payload.yaml_content, encoding="utf-8")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Unable to write YAML file: {exc}") from exc

    base = _base_dir()
    json_path = yaml_path.with_suffix(".json")
    json_rel: Optional[str] = None
    if payload.json_content is not None:
        stripped = payload.json_content.strip()
        if not stripped:
            if json_path.exists():
                try:
                    json_path.unlink()
                except Exception as exc:
                    raise HTTPException(status_code=500, detail=f"Unable to delete JSON file: {exc}") from exc
        else:
            try:
                json_payload = json.loads(payload.json_content)
            except json.JSONDecodeError as exc:
                raise HTTPException(status_code=400, detail=f"Invalid JSON content: {exc}") from exc
            _write_json(json_path, json_payload)
        if json_path.exists():
            try:
                json_rel = str(json_path.relative_to(base))
            except Exception:
                json_rel = str(json_path)
    else:
        if json_path.exists():
            try:
                json_rel = str(json_path.relative_to(base))
            except Exception:
                json_rel = str(json_path)

    stat = yaml_path.stat()
    try:
        yaml_rel = str(yaml_path.relative_to(base))
    except Exception:
        yaml_rel = str(yaml_path)
    return UploadTemplateResponse(
        status="success",
        yaml_path=yaml_rel,
        json_path=json_rel,
        name=yaml_path.name,
        size=stat.st_size,
        modified_at=datetime.fromtimestamp(stat.st_mtime).isoformat(),
        message="Template updated.",
    )

@router.delete("/templates/detail", response_model=SimpleStatusResponse)
def delete_template(
    template_path: str = Query(..., description="Path under ~/ensembles, e.g. demos/floppybird.yaml")
) -> SimpleStatusResponse:
    yaml_path = _resolve_template_path(template_path)
    if not yaml_path.exists():
        raise HTTPException(status_code=404, detail="Template not found")
    try:
        yaml_path.unlink()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Unable to delete YAML file: {exc}") from exc
    json_path = yaml_path.with_suffix(".json")
    if json_path.exists():
        try:
            json_path.unlink()
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Unable to delete JSON file: {exc}") from exc
    return SimpleStatusResponse(status="success", message="Template deleted.")
