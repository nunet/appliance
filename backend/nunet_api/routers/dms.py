# nunet_api/app/routers/dms.py
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Depends
import os
import logging
from ..schemas import (
    InstallStatus, StructuredLogs, DmsStatus, CommandResult, PeerInfo, ResourcesInfo,
    ConnectedPeers, ConnectedPeer, FullStatusCombined, DmsLogsResponse
)
from fastapi import Query
from pathlib import Path
from ..adapters import normalize_dms_status, parse_connected_peers, build_full_status_summary
from pathlib import Path
import json, subprocess
from modules.dms_manager import DMSManager
from modules.path_constants import DMS_INIT_SCRIPT
from modules.dms_utils import (
    get_cached_dms_peer_raw,
    get_cached_dms_resource_info,
    get_cached_dms_status_info,
    invalidate_all_dms_caches,
)
from modules.utils import get_dms_updates, trigger_dms_update

router = APIRouter()

def _run_captured(
    argv: List[str],
    *,
    env: Optional[dict] = None,
    cwd: Optional[str | Path] = None,
    timeout: int = 3600,
    label: str = "command"
) -> CommandResult:
    """
    Run a command, capture stdout/stderr, and return a CommandResult.
    Uses sudo -n patterns at call sites to avoid blocking for passwords.
    """
    try:
        cp = subprocess.run(
            argv,
            text=True,
            capture_output=True,
            env=env,
            cwd=str(cwd) if isinstance(cwd, Path) else cwd,
            timeout=timeout,
        )
        status = "success" if cp.returncode == 0 else "error"
        msg = f"{label} completed" if cp.returncode == 0 else f"{label} failed"
        return CommandResult(
            status=status,
            message=msg,
            stdout=cp.stdout or "",
            stderr=cp.stderr or "",
            returncode=cp.returncode,
        )
    except subprocess.TimeoutExpired as e:
        return CommandResult(
            status="error",
            message=f"{label} timed out after {timeout}s",
            stdout=(e.stdout or "") if hasattr(e, "stdout") else "",
            stderr=(e.stderr or "") if hasattr(e, "stderr") else "",
            returncode=None,
        )
    except Exception as e:
        return CommandResult(
            status="error",
            message=f"Unexpected error running {label}: {e}",
            stdout="",
            stderr="",
            returncode=None,
        )


def _run_many(commands: List[List[str]], *, env: Optional[dict] = None, label: str = "batch") -> CommandResult:
    """
    Run several commands sequentially, aggregate outputs.
    """
    all_out, all_err = [], []
    last_rc = 0
    for argv in commands:
        cp = subprocess.run(argv, text=True, capture_output=True, env=env)
        cmd_txt = "$ " + " ".join(argv)
        all_out.append(f"{cmd_txt}\n{cp.stdout or ''}")
        all_err.append(f"{cmd_txt}\n{cp.stderr or ''}")
        if cp.returncode != 0:
            last_rc = cp.returncode
    status = "success" if last_rc == 0 else "error"
    msg = f"{label} completed" if status == "success" else f"{label} had failures"
    return CommandResult(
        status=status,
        message=msg,
        stdout="\n".join(all_out).strip(),
        stderr="\n".join(all_err).strip(),
        returncode=last_rc,
    )

def get_mgr():
    # Single manager instance; expand to DI/container if you like
    return DMSManager()

@router.get("/version", response_model=str)
def version(mgr: DMSManager = Depends(get_mgr)):
    return mgr.get_dms_version()

@router.get("/check-updates", response_model=str)
def check_dms_updates():
    """Check if a newer DMS version is available."""
    return get_dms_updates()

@router.get("/install", response_model=InstallStatus)
def install_status(mgr: DMSManager = Depends(get_mgr)):
    info = mgr.check_dms_installation()
    return InstallStatus(**info)

@router.get("/status", response_model=DmsStatus)
def status(
    fresh: bool = Query(
        False,
        alias="refresh",
        description="When true, bypass the DMS status cache for a fresh read.",
    )
):
    raw = get_cached_dms_status_info(force_refresh=fresh) or {}
    return DmsStatus(**normalize_dms_status(raw))

@router.get("/status/full", response_model=ResourcesInfo)
def status_full(
    fresh: bool = Query(
        False,
        alias="refresh",
        description="When true, bypass the DMS resource cache for a fresh read.",
    )
):
    resources = get_cached_dms_resource_info(force_refresh=fresh) or {}
    return ResourcesInfo(
        onboarding_status=resources.get("onboarding_status", "Unknown"),
        free_resources=resources.get("free_resources", "Unknown"),
        allocated_resources=resources.get("allocated_resources", "Unknown"),
        onboarded_resources=resources.get("onboarded_resources", "Unknown"),
    )


@router.get("/status/resources", response_model=ResourcesInfo)
def status_resources(
    fresh: bool = Query(
        False,
        alias="refresh",
        description="When true, bypass the DMS resource cache for a fresh read.",
    )
):
    resources = get_cached_dms_resource_info(force_refresh=fresh) or {}
    return ResourcesInfo(
        onboarding_status=resources.get("onboarding_status", "Unknown"),
        free_resources=resources.get("free_resources", "Unknown"),
        allocated_resources=resources.get("allocated_resources", "Unknown"),
        onboarded_resources=resources.get("onboarded_resources", "Unknown"),
    )

@router.get("/peer-id", response_model=str)
def peer_id(mgr: DMSManager = Depends(get_mgr)):
    pid = mgr.get_peer_id()
    if not pid:
        raise HTTPException(status_code=404, detail="Peer ID not available")
    return pid

@router.get("/peers/self", response_model=PeerInfo)
def self_peer(mgr: DMSManager = Depends(get_mgr)):
    info = mgr.get_self_peer_info()
    if not info:
        raise HTTPException(status_code=503, detail="Peer info unavailable")
    return PeerInfo(**info)

@router.post("/restart", response_model=CommandResult)
def restart(mgr: DMSManager = Depends(get_mgr)):
    result = mgr.restart_dms()

    # Archive onboarding state if onboarding was completed
    try:
        from modules.onboarding_manager import OnboardingManager
        onboarding_mgr = OnboardingManager()
        state = onboarding_mgr.state
        if state.get("step") == "complete" and state.get("completed"):
            org_data = state.get("org_data", {})
            org_name = org_data.get("name", "Unknown")
            onboarding_mgr.mark_onboarding_complete(org_name)
    except Exception as e:
        logging.error(f"Error archiving onboarding state during DMS restart: {e}")

    response = CommandResult(**result)
    invalidate_all_dms_caches()
    return response

@router.post("/stop", response_model=CommandResult)
def stop():
    cmds = [
        ["sudo", "-n", "systemctl", "stop", "nunetdms"],
        ["sudo", "-n", "systemctl", "status", "nunetdms", "--no-pager", "--full"],
    ]
    result = _run_many(cmds, label="dms stop")
    invalidate_all_dms_caches()
    return result

@router.post("/enable", response_model=CommandResult)
def enable():
    cmds = [
        ["sudo", "-n", "systemctl", "enable", "loadubuntukeyring"],
        ["sudo", "-n", "systemctl", "enable", "loadnunetkeyring"],
        ["sudo", "-n", "systemctl", "enable", "nunetdms"],
        ["sudo", "-n", "systemctl", "start", "loadubuntukeyring"],
        ["sudo", "-n", "systemctl", "start", "loadnunetkeyring"],
        ["sudo", "-n", "systemctl", "status", "nunetdms", "--no-pager", "--full"],
    ]
    result = _run_many(cmds, label="dms enable")
    invalidate_all_dms_caches()
    return result

@router.post("/disable", response_model=CommandResult)
def disable():
    cmds = [
        ["sudo", "-n", "systemctl", "disable", "nunetdms"],
        ["sudo", "-n", "systemctl", "disable", "loadnunetkeyring"],
        ["sudo", "-n", "systemctl", "disable", "loadubuntukeyring"],
        ["sudo", "-n", "systemctl", "status", "nunetdms", "--no-pager", "--full"],
    ]
    result = _run_many(cmds, label="dms disable")
    invalidate_all_dms_caches()
    return result

@router.post("/onboard", response_model=CommandResult)
def onboard(mgr: DMSManager = Depends(get_mgr)):
    result = CommandResult(**mgr.onboard_compute())
    invalidate_all_dms_caches()
    return result

@router.post("/offboard", response_model=CommandResult)
def offboard(mgr: DMSManager = Depends(get_mgr)):
    result = CommandResult(**mgr.offboard_compute())
    invalidate_all_dms_caches()
    return result

@router.get("/resources/allocated", response_model=dict)
def resources_allocated(mgr: DMSManager = Depends(get_mgr)):
    # Return raw JSON string or parse if preferred
    out = mgr.get_resource_allocation()
    # Try to decode if it looks like JSON in message
    try:
        return json.loads(out["message"])
    except Exception:
        return out

@router.post("/init", response_model=CommandResult)
def init():
    """
    Non-interactive init. Captures stdout/stderr and returns them.
    If the script prompts, this will fail or hang; prefer to make the script non-interactive.
    """
    env = os.environ.copy()
    dms_pw = _get_dms_passphrase()
    if dms_pw:
        # ensure sudo preserves this
        env["DMS_PASSPHRASE"] = dms_pw

    script_path = DMS_INIT_SCRIPT
    if not script_path.exists():
        return CommandResult(status="error", message=f"Script not found: {script_path}", returncode=2)

    # -n: non-interactive fail if sudo password is required
    # -E: preserve environment (so DMS_PASSPHRASE survives)
    argv = ["sudo", "-n", "-E", "-u", "ubuntu", str(script_path)]
    result = _run_captured(argv, env=env, label="dms init")
    invalidate_all_dms_caches()
    return result


@router.post("/update", response_model=CommandResult)
def update():
    """
    Triggers the nunet-dms-updater systemd service to update DMS asynchronously.
    This avoids blocking the API process and prevents the API from being killed
    when the updater restarts services.
    """
    result = trigger_dms_update()
    invalidate_all_dms_caches()
    return CommandResult(**result)




def _get_dms_passphrase() -> str | None:
    try:
        key_id = subprocess.run(["keyctl", "request", "user", "dms_passphrase"], text=True, capture_output=True, check=True).stdout.strip()
        if not key_id:
            return None
        return subprocess.run(["keyctl", "pipe", key_id], text=True, capture_output=True, check=True).stdout.strip() or None
    except Exception:
        return None


@router.get("/peers/connected", response_model=ConnectedPeers)
def peers_connected(
    mgr: DMSManager = Depends(get_mgr),
    fresh: bool = Query(
        False,
        alias="refresh",
        description="When true, bypass the peer cache for a fresh snapshot.",
    ),
):
    """
    Returns the list of connected peers, normalized into JSON.
    Uses cached CLI output when available to avoid repeated subprocess calls.
    """
    stdout = get_cached_dms_peer_raw(force_refresh=fresh)
    if not stdout:
        res = mgr.view_peer_details()
        if not res or res.get("status") != "success":
            raise HTTPException(status_code=503, detail=res.get("message", "Peer list unavailable"))
        stdout = res.get("message") or ""

    parsed = parse_connected_peers(stdout)
    peers_models = [ConnectedPeer(**p) for p in parsed]
    raw_payload = None if peers_models else stdout
    return ConnectedPeers(count=len(peers_models), peers=peers_models, raw=raw_payload)

@router.get("/status/combined", response_model=FullStatusCombined)
def status_combined(
    fresh: bool = Query(
        False,
        alias="refresh",
        description="When true, bypass the DMS caches for a fresh combined snapshot.",
    )
):
    """
    Combined resources + DMS status as JSON, plus a human-readable summary text
    (mirrors show_full_status without colors).
    """
    status_info = get_cached_dms_status_info(force_refresh=fresh) or {}
    resources_dict = get_cached_dms_resource_info(force_refresh=fresh) or {}

    dms_norm = normalize_dms_status(status_info)
    resources = ResourcesInfo(
        onboarding_status=resources_dict.get("onboarding_status", "Unknown"),
        free_resources=resources_dict.get("free_resources", "Unknown"),
        allocated_resources=resources_dict.get("allocated_resources", "Unknown"),
        onboarded_resources=resources_dict.get("onboarded_resources", "Unknown"),
    )
    dms = DmsStatus(**dms_norm)

    summary_source = {**resources_dict, **status_info, **dms_norm}
    summary_text = build_full_status_summary(summary_source)

    return FullStatusCombined(resources=resources, dms=dms, summary_text=summary_text)

@router.get("/logs", response_model=CommandResult)
def dms_logs(lines: int = 200):
    """
    Fetch recent DMS service logs via journalctl.
    """
    argv = ["sudo", "-n", "journalctl", "-u", "nunetdms", "-n", str(lines), "--no-pager", "--output=short-iso"]
    return _run_captured(argv, label="dms logs")

@router.get("/logs/filtered", response_model=DmsLogsResponse)
def dms_logs_filtered(
    dms_query: str | None = Query(default=None, description="Optional jq filter for DMS logs"),
    dms_lines: int = Query(5000, ge=1, le=10000, description="Number of DMS log lines to scan"),
    dms_view: str = Query(default="compact", description="DMS log view: compact, folded, expanded, map, raw"),
):
    mgr = DMSManager()
    query = dms_query.strip() if isinstance(dms_query, str) else None
    filtered = mgr.get_filtered_dms_logs_general(
        query=query if query else None,
        max_lines=dms_lines,
        view=dms_view,
    )
    rc = filtered.get("returncode")
    status = "success" if rc in (0, None) else "error"
    stderr = (filtered.get("stderr") or "").strip()
    stdout = (filtered.get("stdout") or "").strip()
    dms_text = stdout
    if not dms_text and status != "success" and stderr:
        dms_text = f"[stderr]\n{stderr}"
    return DmsLogsResponse(
        status=status,
        message=stderr if status != "success" else "",
        dms=dms_text,
        dms_logs=filtered,
    )

@router.get("/logs/structured", response_model=StructuredLogs, response_model_exclude_none=True)
def logs_structured(
    alloc_dir: str | None = Query(None, description="Absolute path under /home/nunet/nunet/deployments/.../allocX"),
    lines: int = Query(200, ge=1, le=5000, description="How many lines from the end to return")
):
    """
    Return separate, structured logs:
      - Allocation stdout/stderr (if alloc_dir provided)
      - DMS service logs (journalctl)
    """
    mgr = DMSManager()
    data = mgr.get_structured_logs(Path(alloc_dir) if alloc_dir else None, lines=lines)
    # map dict to Pydantic model (validates and filters)
    return StructuredLogs(**data)
