import json, subprocess, os
from modules.dms_manager import DMSManager
from fastapi import APIRouter, HTTPException, Depends, Query, Body, WebSocket
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from ..utils.pty_bridge import run_pty_ws
from modules.ensemble_manager_v2 import EnsembleManagerV2
from modules.dms_utils import run_dms_command_with_passphrase
from ..schemas import (
    DeploymentsWebResponse, DeploymentWebItem,
    RunningListResponse, RunningItem,
    ManifestTextResponse, LogsTextResponse,
    DeployRequest, DeployResponse,
    ShutdownResponse, TemplatesListItem, TemplatesListResponse,
    CopyRequest, CopyResponse, DownloadExamplesRequest, SimpleStatusResponse
)

from modules.ensemble_utils import (
    scan_ensembles_directory, load_ensemble_metadata, process_yaml_template,
    validate_form_data, save_deployment_instance, get_deployment_options
)



router = APIRouter()

def _metadata_without_peer_requirement(meta: dict | None) -> dict | None:
    """
    Return a shallow copy of metadata with fields.peer_id.required = False.
    Used for non_targeted deployments so validation does not force peer_id.
    """
    if not meta:
        return meta
    m = dict(meta)
    fields = dict(m.get("fields", {}))
    if "peer_id" in fields:
        f = dict(fields["peer_id"])
        f["required"] = False
        fields["peer_id"] = f
        m["fields"] = fields
    return m

def _autofill_local_peer(values: dict) -> dict:
    """
    If peer_id is absent, try to inject the local peer id.
    """
    v = dict(values or {})
    if "peer_id" not in v or not v["peer_id"]:
        try:
            from modules.dms_manager import DMSManager
            dm = DMSManager()
            local_peer = dm.get_self_peer_info().get("peer_id")
            if local_peer:
                v["peer_id"] = local_peer
        except Exception:
            # Swallow—validation will catch if still required
            pass
    return v

def _resolve_template_in_base(mgr: EnsembleManagerV2, p: str) -> Path:
    """
    Resolve a template path relative to ~/ensembles and ensure it stays inside.
    Accepts either a relative path like 'rare-evo/floppybird.yaml' or a plain filename in the root.
    """
    candidate = _resolve_path(mgr, p)  # uses base_dir for relative paths
    base = mgr.base_dir.resolve()
    c_res = candidate.resolve()
    if not str(c_res).startswith(str(base)):
        raise HTTPException(status_code=400, detail="Template path must be inside ~/ensembles")
    if not c_res.exists() or not c_res.is_file():
        raise HTTPException(status_code=404, detail=f"Template not found: {c_res}")
    return c_res

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

def get_mgr():
    return EnsembleManagerV2()


def _resolve_path(mgr: EnsembleManagerV2, p: str) -> Path:
    """Resolve absolute vs relative (relative to ~/ensembles) without changing business logic."""
    path = Path(p).expanduser()
    return path if path.is_absolute() else (mgr.base_dir / path)



def _resolve_allocation_choice(
    mgr: EnsembleManagerV2,
    deployment_id: str,
    requested_alloc: str | None,
) -> Tuple[Optional[str], List[str]]:
    allocs = mgr.get_deployment_allocations(deployment_id) or []
    if not allocs:
        return None, allocs

    if not requested_alloc:
        if len(allocs) == 1:
            return allocs[0], allocs
        raise HTTPException(
            status_code=400,
            detail={"error": "multiple_allocations", "allocations": allocs},
        )

    requested_clean = requested_alloc.strip()
    if not requested_clean:
        raise HTTPException(
            status_code=400,
            detail={"error": "invalid_allocation", "provided": requested_alloc, "allocations": allocs},
        )

    requested_key = requested_clean.lower()
    # Accept either the full allocation id or a unique suffix (e.g. "alloc1").
    normalized = {alloc.lower(): alloc for alloc in allocs}

    if requested_key in normalized:
        return normalized[requested_key], allocs

    suffix_map: Dict[str, List[str]] = {}
    for alloc in allocs:
        suffix = alloc.rsplit('.', 1)[-1].lower()
        suffix_map.setdefault(suffix, []).append(alloc)

    matches = suffix_map.get(requested_key, [])
    if len(matches) == 1:
        return matches[0], allocs

    if len(matches) > 1:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "ambiguous_allocation",
                "provided": requested_alloc,
                "matching_allocations": matches,
                "allocations": allocs,
            },
        )

    raise HTTPException(
        status_code=400,
        detail={"error": "invalid_allocation", "provided": requested_alloc, "allocations": allocs},
    )


@router.get("/deployments", response_model=DeploymentsWebResponse)
def list_deployments(mgr: EnsembleManagerV2 = Depends(get_mgr)):
    res = mgr.get_deployments_for_web()
    if res.get("status") != "success":
        raise HTTPException(status_code=500, detail=res.get("message", "Failed to get deployments"))

    items: List[DeploymentWebItem] = []
    for d in res.get("deployments", []):
        ts = str(d.get("timestamp"))
        # ensure isoformat
        if isinstance(ts, datetime):
            ts = ts.isoformat()
        items.append(DeploymentWebItem(
            id=d.get("id", ""),
            status=d.get("status", ""),
            type=d.get("type", ""),
            timestamp=str(ts),
            ensemble_file=d.get("ensemble_file", ""),
        ))

    return DeploymentsWebResponse(
        status=res["status"], deployments=items, count=res.get("count", len(items))
    )


@router.get("/deployments/running", response_model=RunningListResponse)
def list_running_table(mgr: EnsembleManagerV2 = Depends(get_mgr)):
    res = mgr.view_running_ensembles()
    if res.get("status") != "success":
        raise HTTPException(status_code=500, detail=res.get("message", "Failed to get running deployments"))

    items_out: List[RunningItem] = []
    for pair in res.get("items", []):
        # pair is (id, info)
        dep_id, info = pair
        ts = info.get("timestamp")
        ts_s = ts.isoformat() if isinstance(ts, datetime) else str(ts)
        items_out.append(RunningItem(
            id=dep_id,
            status=str(info.get("status", "")),
            active=bool(info.get("active", False)),
            type=str(info.get("type", "")),
            timestamp=ts_s,
            file_name=str(info.get("file_name", "")),
        ))

    return RunningListResponse(
        status="success",
        message=res.get("message", ""),
        count=res.get("count", len(items_out)),
        items=items_out
    )


@router.get("/deployments/{deployment_id}/status")
def deployment_status(deployment_id: str, mgr: EnsembleManagerV2 = Depends(get_mgr)):
    return mgr.get_deployment_status(deployment_id)


@router.get("/deployments/{deployment_id}/manifest", response_model=ManifestTextResponse)
def deployment_manifest_text(deployment_id: str, mgr: EnsembleManagerV2 = Depends(get_mgr)):
    res = mgr.get_deployment_manifest_text(deployment_id)
    if res.get("status") != "success":
        raise HTTPException(status_code=500, detail=res.get("message", "Failed to get manifest"))
    return ManifestTextResponse(status="success", message=res.get("manifest_text", res.get("message", "")))


@router.get("/deployments/{deployment_id}/allocations", response_model=List[str])
def allocations_for_deployment(deployment_id: str, mgr: EnsembleManagerV2 = Depends(get_mgr)):
    return mgr.get_deployment_allocations(deployment_id)


def _format_log_section(label: str, entry: dict | None) -> str:
    lines = [f"=== {label} ==="]
    if not entry:
        lines.append(f"No {label.lower()} logs available.")
        return "\n".join(lines)
    path_str = entry.get("path")
    if path_str:
        lines.append(f"Path: {path_str}")
    content = entry.get("content")
    error = entry.get("error")
    exists = entry.get("exists")
    if content:
        lines.append(content.rstrip("\n"))
    elif error:
        lines.append(f"(error: {error})")
    elif exists:
        lines.append("(empty log file)")
    else:
        lines.append("No log file found.")
    return "\n".join(lines)


def _format_dms_section(bundle: dict | None) -> str:
    lines = ["=== DMS LOG ENTRIES ==="]
    if not bundle:
        lines.append("No DMS log data available.")
        return "\n".join(lines)
    source = bundle.get("source")
    if source:
        lines.append(f"Source: {source}")
    stdout = (bundle.get("stdout") or "").strip()
    stderr = (bundle.get("stderr") or "").strip()
    if stdout:
        lines.append(stdout)
    else:
        lines.append("No entries found in DMS log.")
    if stderr:
        lines.append("")
        lines.append("[stderr]")
        lines.append(stderr)
    returncode = bundle.get("returncode")
    if returncode not in (0, None):
        lines.append("")
        lines.append(f"[returncode] {returncode}")
    return "\n".join(lines)

@router.post("/deployments/{deployment_id}/logs/request", response_model=SimpleStatusResponse)
def request_deployment_logs(
    deployment_id: str,
    allocation: str | None = Query(
        default=None,
        description="Optional allocation name if multiple exist",
    ),
    mgr: EnsembleManagerV2 = Depends(get_mgr),
):
    selected_alloc, allocs = _resolve_allocation_choice(mgr, deployment_id, allocation)
    if not selected_alloc:
        if allocs:
            raise HTTPException(
                status_code=400,
                detail={"error": "allocation_required", "allocations": allocs},
            )
        raise HTTPException(
            status_code=400,
            detail={
                "error": "no_allocations",
                "message": "Deployment has no allocations available.",
            },
        )

    cmd = [
        "nunet",
        "-c",
        "dms",
        "actor",
        "cmd",
        "/dms/node/deployment/logs",
        "--id",
        deployment_id,
        "--allocation",
        selected_alloc,
    ]

    try:
        result = run_dms_command_with_passphrase(
            cmd,
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        message = (exc.stderr or exc.stdout or str(exc)).strip() or "Failed to request logs."
        raise HTTPException(
            status_code=502,
            detail={"error": "log_request_failed", "message": message},
        ) from exc
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=500,
            detail={"error": "nunet_not_found", "message": "nunet CLI not available"},
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={"error": "log_request_error", "message": str(exc)},
        ) from exc

    message = f"Log request triggered for allocation {selected_alloc}."
    stdout = (result.stdout or "").strip()
    stderr = (result.stderr or "").strip()

    if stdout:
        try:
            payload = json.loads(stdout)
            if isinstance(payload, dict):
                message = payload.get("message") or payload.get("status") or json.dumps(payload)
            else:
                message = stdout
        except json.JSONDecodeError:
            message = stdout
    elif stderr:
        message = stderr

    return SimpleStatusResponse(status="success", message=message)

@router.get("/deployments/{deployment_id}/logs", response_model=LogsTextResponse)
def deployment_logs_text(
    deployment_id: str,
    allocation: str | None = Query(default=None, description="Optional allocation name if multiple exist"),
    mgr: EnsembleManagerV2 = Depends(get_mgr)
):
    """
    Non-interactive logs endpoint. If a deployment has multiple allocations and none is given,
    return 400 with available choices (so the API never blocks on input()).
    """
    selected_alloc, _ = _resolve_allocation_choice(mgr, deployment_id, allocation)

    alloc_dir = None
    if selected_alloc:
        alloc_dir = Path("/home/nunet/nunet/deployments") / deployment_id / selected_alloc

    try:
        dm = DMSManager()
        structured = dm.get_structured_logs(alloc_dir, lines=400)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={"error": "log_fetch_failed", "message": str(exc)},
        ) from exc

    status_text = structured.get("status") or "success"
    header_msg = structured.get("message") or ""

    lines_out = ["Log Contents:"]
    header_line = f"[{status_text.upper()}]"
    if header_msg:
        header_line = f"{header_line} {header_msg}"
    lines_out.append(header_line)

    if selected_alloc and alloc_dir:
        lines_out.append(f"Allocation: {selected_alloc}")
        lines_out.append(f"Deployment directory: {alloc_dir}")
    else:
        lines_out.append("Allocation: N/A")

    alloc_bundle = structured.get("allocation") or {}
    stdout_section = alloc_bundle.get("stdout")
    stderr_section = alloc_bundle.get("stderr")

    lines_out.append("")
    lines_out.append(_format_log_section("STDOUT", stdout_section))
    lines_out.append("")
    lines_out.append(_format_log_section("STDERR", stderr_section))
    lines_out.append("")
    lines_out.append(_format_dms_section(structured.get("dms_logs")))

    log_message = "\n".join(lines_out).strip()
    return LogsTextResponse(status=status_text, message=log_message)

@router.post("/deployments", response_model=DeployResponse)
def deploy_ensemble(payload: DeployRequest, mgr: EnsembleManagerV2 = Depends(get_mgr)):
    file_path = _resolve_path(mgr, payload.file_path)
    res = mgr.deploy_ensemble(file_path, timeout=payload.timeout or 60)
    if res.get("status") != "success":
        raise HTTPException(status_code=500, detail=res.get("message", "Deployment failed"))
    return DeployResponse(status="success", message=res.get("message", ""), deployment_id=res.get("deployment_id"))


@router.post("/deployments/{deployment_id}/shutdown", response_model=ShutdownResponse)
def shutdown_deployment(deployment_id: str, mgr: EnsembleManagerV2 = Depends(get_mgr)):
    res = mgr.shutdown_deployment(deployment_id)
    if res.get("status") != "success":
        raise HTTPException(status_code=500, detail=res.get("message", "Shutdown failed"))
    return ShutdownResponse(status="success", message=res.get("message", ""))


@router.get("/templates", response_model=TemplatesListResponse)
def list_templates(mgr: EnsembleManagerV2 = Depends(get_mgr)):
    items = mgr.get_ensemble_files()
    out: List[TemplatesListItem] = []
    for idx, path in items:
        try:
            rel = path.relative_to(mgr.base_dir)
        except Exception:
            rel = path.name
        out.append(TemplatesListItem(index=idx, name=path.name, path=str(path), relative_path=str(rel)))
    return TemplatesListResponse(items=out)


@router.post("/templates/copy", response_model=CopyResponse)
def copy_template(payload: CopyRequest, mgr: EnsembleManagerV2 = Depends(get_mgr)):
    src = _resolve_path(mgr, payload.source)
    dst = _resolve_path(mgr, payload.dest)
    res = mgr.copy_ensemble(src, dst)
    return CopyResponse(status=res.get("status", "error"), message=res.get("message", ""))


@router.post("/examples/download", response_model=SimpleStatusResponse)
def download_examples(payload: DownloadExamplesRequest, mgr: EnsembleManagerV2 = Depends(get_mgr)):
    res = mgr.download_example_ensembles(
        repo=payload.repo or mgr.repo,
        branch=payload.branch,
        source_dir=payload.source_dir or mgr.source_dir,
        target_dir=Path(payload.target_dir).expanduser() if payload.target_dir else None,
    )
    return SimpleStatusResponse(status=res.get("status", "error"), message=res.get("message", ""))


@router.get("/deployments/{deployment_id}/manifest/raw", response_model=Dict[str, Any])
def deployment_manifest_raw(deployment_id: str):
    """
    Return the raw JSON manifest as produced by nunet.
    This is a direct pass-through (parsed) of the CLI output:
    `nunet -c dms actor cmd /dms/node/deployment/manifest -i <id>`
    """
    try:
        cp = run_dms_command_with_passphrase(
            ["nunet", "-c", "dms", "actor", "cmd", "/dms/node/deployment/manifest", "-i", deployment_id],
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=502, detail=f"nunet manifest failed: {e}")

    try:
        data = json.loads(cp.stdout)
    except json.JSONDecodeError as je:
        raise HTTPException(status_code=502, detail=f"nunet returned invalid JSON: {je}")
    return data


def _get_dms_passphrase() -> str | None:
    try:
        key_id = subprocess.run(["keyctl", "request", "user", "dms_passphrase"], text=True, capture_output=True, check=True).stdout.strip()
        if not key_id:
            return None
        return subprocess.run(["keyctl", "pipe", key_id], text=True, capture_output=True, check=True).stdout.strip() or None
    except Exception:
        return None

@router.websocket("/ws/deploy")
async def ws_deploy(ws: WebSocket):
    """
    WebSocket to perform a deployment in real-time:
    Client should connect with query params:
      file=<abs or relative to ~/ensembles>  timeout=<seconds, default 60>
    Server streams stdout/stderr and exit event.
    """
    await ws.accept()

    params = ws.query_params
    file_path = params.get("file")
    timeout = params.get("timeout") or "60"

    if not file_path:
        await ws.send_json({"type": "error", "message": "Missing 'file' query param"})
        await ws.close(code=4400)
        return

    mgr = EnsembleManagerV2()
    # resolve path relative to ~/ensembles
    p = (mgr.base_dir / file_path).expanduser()
    if not p.is_absolute():
        p = (mgr.base_dir / file_path).resolve()

    env = os.environ.copy()
    dms_pw = _get_dms_passphrase()
    if dms_pw:
        env["DMS_PASSPHRASE"] = dms_pw

    argv = [
        "nunet", "-c", "dms", "actor", "cmd", "/dms/node/deployment/new",
        "-t", f"{int(timeout)}s", "-f", str(p)
    ]

    # PTY streaming; UI can watch stdout and parse EnsembleID as it appears.
    await run_pty_ws(ws, argv, env=env, cwd=None, label="deploy")


@router.get("/templates/yamls", response_model=dict)
def list_yaml_templates(
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    page_size: int = Query(10, ge=1, le=100, description="Items per page"),
    with_content: bool = Query(False, description="Include file contents inline"),
    mgr: EnsembleManagerV2 = Depends(get_mgr),
):
    """
    List YAML ensemble files (for deployment) under ~/ensembles.
    Frontend can use 'path' with your WS deploy endpoint: file=<path>
    """
    root = mgr.base_dir
    yaml_files = sorted(list(root.rglob("*.yaml")) + list(root.rglob("*.yml")))

    items = []
    for yf in yaml_files:
        stat = yf.stat()
        item = {
            "category": _category_for(yf, root),
            "name": yf.name,
            "stem": yf.stem,
            "path": _relpath(yf, root),
            "size": stat.st_size,
            "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
        }
        if with_content:
            try:
                with open(yf, "r", encoding="utf-8") as f:
                    item["content"] = f.read()
            except Exception as e:
                item["content_error"] = str(e)
        items.append(item)

    # Sort by category then name
    items.sort(key=lambda x: (x["category"].lower(), x["name"].lower()))

    total = len(items)
    start = (page - 1) * page_size
    end = start + page_size
    page_items = items[start:end]

    # Category totals across all items (helpful for UI filters)
    category_totals: Dict[str, int] = {}
    for it in items:
        category_totals[it["category"]] = category_totals.get(it["category"], 0) + 1

    return {
        "root": str(root),
        "page": page,
        "page_size": page_size,
        "total": total,
        "category_totals": category_totals,
        "items": page_items,
    }

@router.get("/deployment-options", response_model=dict)
def deployment_options():
    """
    Returns:
      - local_peer_id
      - known_peers [{id, name}]
      - deployment_types (local | targeted | non_targeted)
    """
    try:
        dm = DMSManager()
        opts = get_deployment_options(dm)  # reuses your utils
        return opts
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get deployment options: {e}")


@router.post("/templates/render", response_model=dict)
def render_template(
    payload: Dict[str, Any] = Body(..., example={
        "template_path": "rare-evo/floppybird.yaml",
        "values": {
            "dns_name": "crappy-bird-fastapi",
            "proxy_port": 8070,
            "bird_color": "red",
            "allocations_alloc1_resources_cpu_cores": 1,
            "allocations_alloc1_resources_ram_size": 1,
            "allocations_alloc1_resources_disk_size": 1,
            "peer_id": "12D3KooW..."
        },
        "deployment_type": "targeted"  # local | targeted | non_targeted
    }),
    mgr: EnsembleManagerV2 = Depends(get_mgr)
):
    template_path = payload.get("template_path")
    values_in = payload.get("values") or {}
    deployment_type = (payload.get("deployment_type") or "local").lower()

    if deployment_type not in ("local", "targeted", "non_targeted"):
        raise HTTPException(status_code=400, detail="deployment_type must be local | targeted | non_targeted")

    tpl = _resolve_template_in_base(mgr, template_path)

    # Load metadata
    meta = load_ensemble_metadata(str(tpl))

    # Adjust values/validation based on type
    if deployment_type == "local":
        values = _autofill_local_peer(values_in)
        meta_for_validation = meta  # peer still required, but we tried to fill it
    elif deployment_type == "non_targeted":
        # Ignore any provided peer_id; relax requirement
        values = dict(values_in)
        values.pop("peer_id", None)
        meta_for_validation = _metadata_without_peer_requirement(meta)
    else:
        # targeted as-is
        values = dict(values_in)
        meta_for_validation = meta

    # Validate after we’ve adjusted for the type
    if meta_for_validation:
        ok, errs = validate_form_data(meta_for_validation, values)
        if not ok:
            return {"status": "error", "errors": errs}

    rendered = process_yaml_template(str(tpl), values, deployment_type)
    if not rendered:
        raise HTTPException(status_code=500, detail="Failed to render template with provided values")

    return {
        "status": "success",
        "template": str(tpl.relative_to(mgr.base_dir)),
        "deployment_type": deployment_type,
        "rendered_yaml": rendered,
        "validation_errors": []
    }

@router.post("/deploy/from-template", response_model=dict)
def deploy_from_template(
    payload: Dict[str, Any] = Body(..., example={
        "template_path": "rare-evo/floppybird.yaml",
        "values": {
            "dns_name": "crappy-bird-fastapi",
            "proxy_port": 8070,
            "bird_color": "red",
            "allocations_alloc1_resources_cpu_cores": 1,
            "allocations_alloc1_resources_ram_size": 1,
            "allocations_alloc1_resources_disk_size": 20,
            "peer_id": "12D3KooW..."  # required if targeted; optional otherwise
        },
        "deployment_type": "local",   # local | targeted | non_targeted
        "timeout": 60,
        "save_instance": True
    }),
    mgr: EnsembleManagerV2 = Depends(get_mgr)
):
    template_path = payload.get("template_path")
    values_in = payload.get("values") or {}
    deployment_type = (payload.get("deployment_type") or "local").lower()
    timeout = int(payload.get("timeout") or 60)
    save_instance = bool(payload.get("save_instance", True))

    if deployment_type not in ("local", "targeted", "non_targeted"):
        raise HTTPException(status_code=400, detail="deployment_type must be local | targeted | non_targeted")

    tpl = _resolve_template_in_base(mgr, template_path)

    # Load metadata
    meta = load_ensemble_metadata(str(tpl))

    # Prepare values per deployment type
    if deployment_type == "targeted":
        values = dict(values_in)
        if not values.get("peer_id"):
            raise HTTPException(status_code=400, detail="peer_id is required for targeted deployments")
        meta_for_validation = meta
    elif deployment_type == "local":
        values = _autofill_local_peer(values_in)
        # If still no peer_id, fail with helpful message
        if not values.get("peer_id"):
            raise HTTPException(
                status_code=400,
                detail="Could not determine local peer_id. Ensure DMS is running, or provide peer_id explicitly."
            )
        meta_for_validation = meta
    else:  # non_targeted
        values = dict(values_in)
        values.pop("peer_id", None)  # explicitly ignore
        meta_for_validation = _metadata_without_peer_requirement(meta)

    # Validate AFTER adjusting values/requirements
    if meta_for_validation:
        ok, errs = validate_form_data(meta_for_validation, values)
        if not ok:
            raise HTTPException(status_code=400, detail={"error": "validation_failed", "errors": errs})

    # Render
    rendered = process_yaml_template(str(tpl), values, deployment_type)
    if not rendered:
        raise HTTPException(status_code=500, detail="Failed to render template with provided values")

    # Save timestamped copy for provenance
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    saved_path: Optional[str] = None
    if save_instance:
        saved_path = save_deployment_instance(str(tpl), rendered, timestamp)
        if not saved_path:
            raise HTTPException(status_code=500, detail="Could not save rendered deployment")
        deploy_path = Path(saved_path)
    else:
        tmp = Path(f"/tmp/{tpl.stem}_{timestamp}.yaml")
        tmp.write_text(rendered, encoding="utf-8")
        deploy_path = tmp

    # Deploy
    res = mgr.deploy_ensemble(deploy_path, timeout=timeout)
    if res.get("status") != "success":
        raise HTTPException(status_code=502, detail=res.get("message", "Deployment failed"))

    return {
        "status": "success",
        "deployment_id": res.get("deployment_id"),
        "saved_path": saved_path or str(deploy_path),
        "message": res.get("message", "")
    }
