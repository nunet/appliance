import json, subprocess, os
from fastapi import WebSocket
from fastapi import APIRouter, HTTPException, Depends, Query
from pathlib import Path
from typing import List, Dict, Any
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



router = APIRouter()

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
