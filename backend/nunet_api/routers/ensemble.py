import json, subprocess, os
from modules.dms_manager import DMSManager
from fastapi import APIRouter, HTTPException, Depends, Query, Body, WebSocket
from pathlib import Path
from typing import List, Dict, Any, Optional
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
    # Figure out allocations
    allocs = mgr.get_deployment_allocations(deployment_id)

    selected_alloc = None
    if allocs:
        if allocation:
            if allocation not in allocs:
                raise HTTPException(
                    status_code=400,
                    detail={"error": "invalid_allocation", "provided": allocation, "allocations": allocs},
                )
            selected_alloc = allocation
        elif len(allocs) == 1:
            selected_alloc = allocs[0]
        else:
            raise HTTPException(
                status_code=400,
                detail={"error": "multiple_allocations", "allocations": allocs},
            )

    log_content = "\nLog Contents:\n"

    # If we have an allocation, fetch stdout/stderr like the CLI version
    if selected_alloc:
        deployment_dir = Path(f"/home/nunet/nunet/deployments/{deployment_id}/{selected_alloc}")
        stdout_path = deployment_dir / "stdout.logs"
        stderr_path = deployment_dir / "stderr.logs"

        log_content += f"\nDeployment directory: {deployment_dir}\n"

        log_content += "\n=== STDOUT ===\n"
        log_content += f"Path: {stdout_path}\n"
        try:
            cp = subprocess.run(["sudo", "cat", str(stdout_path)], text=True, capture_output=True, check=True)
            log_content += cp.stdout
        except subprocess.CalledProcessError as e:
            log_content += f"Error reading stdout: {e}\n"

        log_content += "\n=== STDERR ===\n"
        log_content += f"Path: {stderr_path}\n"
        try:
            cp = subprocess.run(["sudo", "cat", str(stderr_path)], text=True, capture_output=True, check=True)
            log_content += cp.stdout
        except subprocess.CalledProcessError as e:
            log_content += f"Error reading stderr: {e}\n"

    # Always include DMS log grep results (like the CLI)
    dms_log_path = "/home/nunet/logs/nunet-dms.log"
    log_content += f"\n=== DMS LOG ENTRIES ===\nSearching in: {dms_log_path}\n\n"
    try:
        cp = subprocess.run(["sudo", "grep", "-A", "5", "-B", "5", deployment_id, dms_log_path], text=True, capture_output=True)
        log_content += cp.stdout if cp.stdout else "No entries found in DMS log\n"
    except subprocess.CalledProcessError as e:
        log_content += f"Error searching DMS log: {e}\n"

    return LogsTextResponse(status="success", message=log_content)


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

@router.get("/templates/forms", response_model=dict)
def list_form_templates(
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    page_size: int = Query(10, ge=1, le=100, description="Items per page"),
    include_schema: bool = Query(True, description="Include parsed JSON schema"),
    require_yaml_match: bool = Query(True, description="Only include JSONs that have a matching YAML with same stem"),
    mgr: EnsembleManagerV2 = Depends(get_mgr),
):
    """
    List JSON form templates under ~/ensembles, categorized by folder.
    By default, only JSON files that *describe* a YAML (same stem) are returned.
    """
    root = mgr.base_dir
    json_files = sorted(root.rglob("*.json"))

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
            "category": _category_for(jf, root),
            "name": jf.name,
            "stem": jf.stem,
            "path": _relpath(jf, root),
            "yaml_path": _relpath(yaml_match, root) if yaml_match else None,
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
        "root": str(root),
        "page": page,
        "page_size": page_size,
        "total": total,
        "category_totals": category_totals,
        "groups": groups,      # categorized view for the current page
        "items": page_items,   # flat view for the current page
    }

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
    """
    Renders a YAML template (Jinja2) with provided values.
    Does NOT deploy. Optionally validates values against the JSON metadata (if present).
    """
    template_path = payload.get("template_path")
    values = payload.get("values") or {}
    deployment_type = (payload.get("deployment_type") or "local").lower()

    if deployment_type not in ("local", "targeted", "non_targeted"):
        raise HTTPException(status_code=400, detail="deployment_type must be local | targeted | non_targeted")

    # Resolve and validate template path
    tpl = _resolve_template_in_base(mgr, template_path)

    # Validate against metadata if present
    meta = load_ensemble_metadata(str(tpl))
    errors: List[str] = []
    if meta:
        ok, errs = validate_form_data(meta, values)
        if not ok:
            return {"status": "error", "errors": errs}

    # Auto-fill peer_id for local deployments if missing
    if deployment_type == "local" and "peer_id" not in values:
        try:
            dm = DMSManager()
            local_peer = dm.get_self_peer_info().get("peer_id")
            if local_peer:
                values["peer_id"] = local_peer
        except Exception:
            pass  # non-fatal

    rendered = process_yaml_template(str(tpl), values, deployment_type)
    if not rendered:
        raise HTTPException(status_code=500, detail="Failed to render template with provided values")

    return {
        "status": "success",
        "template": str(tpl.relative_to(mgr.base_dir)),
        "deployment_type": deployment_type,
        "rendered_yaml": rendered,
        "validation_errors": errors
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
            "allocations_alloc1_resources_disk_size": 1,
            # optional in 'local' (auto-filled), required in 'targeted'
            "peer_id": "12D3KooW..."  
        },
        "deployment_type": "targeted",   # local | targeted | non_targeted
        "timeout": 60,                   # seconds
        "save_instance": True            # store timestamped copy under /home/ubuntu/nunet/appliance/deployments
    }),
    mgr: EnsembleManagerV2 = Depends(get_mgr)
):
    """
    Renders the template with values, saves a timestamped copy, and deploys it.
    Returns deployment_id on success.
    """
    template_path = payload.get("template_path")
    values = payload.get("values") or {}
    deployment_type = (payload.get("deployment_type") or "local").lower()
    timeout = int(payload.get("timeout") or 60)
    save_instance = bool(payload.get("save_instance", True))

    if deployment_type not in ("local", "targeted", "non_targeted"):
        raise HTTPException(status_code=400, detail="deployment_type must be local | targeted | non_targeted")

    # Resolve template path inside ~/ensembles
    tpl = _resolve_template_in_base(mgr, template_path)

    # Validate against metadata if present
    meta = load_ensemble_metadata(str(tpl))
    if meta:
        ok, errs = validate_form_data(meta, values)
        if not ok:
            raise HTTPException(status_code=400, detail={"error": "validation_failed", "errors": errs})

    # peer handling
    if deployment_type == "targeted":
        if not values.get("peer_id"):
            raise HTTPException(status_code=400, detail="peer_id is required for targeted deployments")
    elif deployment_type == "local":
        if not values.get("peer_id"):
            try:
                dm = DMSManager()
                local_peer = dm.get_self_peer_info().get("peer_id")
                if local_peer:
                    values["peer_id"] = local_peer
            except Exception:
                pass  # if we can't fetch it, the template may still not require it

    # Render
    rendered = process_yaml_template(str(tpl), values, deployment_type)
    if not rendered:
        raise HTTPException(status_code=500, detail="Failed to render template with provided values")

    # Save timestamped copy (to appliance deployments dir)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    saved_path: Optional[str] = None
    if save_instance:
        saved_path = save_deployment_instance(str(tpl), rendered, timestamp)
        if not saved_path:
            raise HTTPException(status_code=500, detail="Could not save rendered deployment")
        deploy_path = Path(saved_path)
    else:
        # If you prefer not to save, write to a temp file under /tmp
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
