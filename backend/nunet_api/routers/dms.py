# nunet_api/app/routers/dms.py
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Depends, WebSocket
import os
from ..schemas import (
    InstallStatus, StructuredLogs, DmsStatus, CommandResult, PeerInfo, ResourcesInfo,ConnectedPeers, ConnectedPeer, FullStatusCombined
)
from fastapi import Query
from pathlib import Path
from ..adapters import normalize_dms_status, parse_connected_peers, build_full_status_summary
from pathlib import Path
import json, subprocess
from ..utils.pty_bridge import run_pty_ws
from modules.dms_manager import DMSManager
from modules.dms_utils import get_dms_status_info, get_dms_resource_info

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

@router.get("/install", response_model=InstallStatus)
def install_status(mgr: DMSManager = Depends(get_mgr)):
    info = mgr.check_dms_installation()
    return InstallStatus(**info)

@router.get("/status", response_model=DmsStatus)
def status(mgr: DMSManager = Depends(get_mgr)):
    raw = mgr.update_dms_status()
    return DmsStatus(**normalize_dms_status(raw))

@router.get("/status/full", response_model=ResourcesInfo)
def status_full(mgr: DMSManager = Depends(get_mgr)):
    # Combines dms + resources; you can also return them separately
    info = mgr.get_full_status_info()
    return ResourcesInfo(
        onboarding_status=info.get("onboarding_status", "Unknown"),
        free_resources=info.get("free_resources", "Unknown"),
        allocated_resources=info.get("allocated_resources", "Unknown"),
        onboarded_resources=info.get("onboarded_resources", "Unknown"),
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
    return CommandResult(**mgr.restart_dms())

@router.post("/stop", response_model=CommandResult)
def stop():
    cmds = [
        ["sudo", "-n", "systemctl", "stop", "nunetdms"],
        ["sudo", "-n", "systemctl", "status", "nunetdms", "--no-pager", "--full"],
    ]
    return _run_many(cmds, label="dms stop")

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
    return _run_many(cmds, label="dms enable")

@router.post("/disable", response_model=CommandResult)
def disable():
    cmds = [
        ["sudo", "-n", "systemctl", "disable", "nunetdms"],
        ["sudo", "-n", "systemctl", "disable", "loadnunetkeyring"],
        ["sudo", "-n", "systemctl", "disable", "loadubuntukeyring"],
        ["sudo", "-n", "systemctl", "status", "nunetdms", "--no-pager", "--full"],
    ]
    return _run_many(cmds, label="dms disable")

@router.post("/onboard", response_model=CommandResult)
def onboard(mgr: DMSManager = Depends(get_mgr)):
    return CommandResult(**mgr.onboard_compute())

@router.post("/offboard", response_model=CommandResult)
def offboard(mgr: DMSManager = Depends(get_mgr)):
    return CommandResult(**mgr.offboard_compute())

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

    script_path = Path("/home/ubuntu/menu/scripts/configure-dms.sh")
    if not script_path.exists():
        return CommandResult(status="error", message=f"Script not found: {script_path}", returncode=2)

    # -n: non-interactive fail if sudo password is required
    # -E: preserve environment (so DMS_PASSPHRASE survives)
    argv = ["sudo", "-n", "-E", "-u", "ubuntu", str(script_path)]
    return _run_captured(argv, env=env, label="dms init")


@router.post("/update", response_model=CommandResult)
def update():
    """
    Captured DMS update (wget + apt). Returns the full logs.
    """
    env = os.environ.copy()
    # Avoid apt interaction
    env["DEBIAN_FRONTEND"] = env.get("DEBIAN_FRONTEND", "noninteractive")

    update_script = r'''
        set -euo pipefail
        arch="$(uname -m | tr '[:upper:]' '[:lower:]')"
        echo "Detected arch: $arch"
        if echo "$arch" | grep -qi 'arm\|aarch'; then
          url="https://d.nunet.io/nunet-dms-arm64-latest.deb"
        elif echo "$arch" | grep -qi 'x86_64\|amd64\|amd'; then
          url="https://d.nunet.io/nunet-dms-amd64-latest.deb"
        else
          echo "Unsupported architecture: $arch" >&2; exit 2
        fi
        echo "Downloading $url ..."
        wget -N "$url" -O dms-latest.deb
        echo "Installing ..."
        sudo -n apt install ./dms-latest.deb -y --allow-downgrades
        echo "Cleaning up ..."
        rm -f dms-latest.deb || true
        echo "✅ Update complete."
    '''
    argv = ["bash", "-lc", update_script]
    return _run_captured(argv, env=env, label="dms update")




def _get_dms_passphrase() -> str | None:
    try:
        key_id = subprocess.run(["keyctl", "request", "user", "dms_passphrase"], text=True, capture_output=True, check=True).stdout.strip()
        if not key_id:
            return None
        return subprocess.run(["keyctl", "pipe", key_id], text=True, capture_output=True, check=True).stdout.strip() or None
    except Exception:
        return None

@router.websocket("/ws/init")
async def ws_dms_init(ws: WebSocket):
    """
    Run the interactive DMS initialization script under a PTY.
    Your UI can answer y/n etc. by sending:
      {"type":"stdin","data":"y\\n"}
    """
    await ws.accept()
    env = os.environ.copy()
    dms_pw = _get_dms_passphrase()
    if dms_pw:
        env["DMS_PASSPHRASE"] = dms_pw

    # Use the same path the manager uses
    script_path = Path("/home/ubuntu/menu/scripts/configure-dms.sh")
    if not script_path.exists():
        await ws.send_json({"type": "error", "message": f"Script missing: {script_path}"})
        await ws.close(code=4404)
        return

    # run as ubuntu like your manager does
    argv = ["sudo", "-u", "ubuntu", str(script_path)]
    await run_pty_ws(ws, argv, env=env, cwd=None, label="init")

@router.post("/onboard", response_model=CommandResult)
def onboard():
    env = os.environ.copy()
    dms_pw = _get_dms_passphrase()
    if dms_pw:
        env["DMS_PASSPHRASE"] = dms_pw

    mgr = DMSManager()
    script_path = (mgr.scripts_dir / "onboard-max.sh")
    if not script_path.exists():
        return CommandResult(status="error", message=f"Script not found: {script_path}", returncode=2)

    argv = ["sudo", "-n", "-E", "-u", "ubuntu", str(script_path)]
    return _run_captured(argv, env=env, label="dms onboard")


@router.websocket("/ws/update")
async def ws_dms_update(ws: WebSocket):
    """
    Stream the DMS update (wget + apt) under a PTY so progress bars render nicely.
    This mirrors your manager's update behavior but streams output live.
    """
    await ws.accept()
    env = os.environ.copy()
    # apt may ask for confirmation if flags change; keep PTY and send "-y"
    # You can also export DEBIAN_FRONTEND=noninteractive to be extra safe:
    env["DEBIAN_FRONTEND"] = env.get("DEBIAN_FRONTEND", "noninteractive")

    # We'll run a small bash that replicates manager.update_dms steps with streaming
    # Detect arch + set URL
    update_script = r'''
        set -euo pipefail
        arch="$(uname -m | tr '[:upper:]' '[:lower:]')"
        echo "Detected arch: $arch"
        if echo "$arch" | grep -qi 'arm\|aarch'; then
          url="https://d.nunet.io/nunet-dms-arm64-latest.deb"
        elif echo "$arch" | grep -qi 'x86_64\|amd64\|amd'; then
          url="https://d.nunet.io/nunet-dms-amd64-latest.deb"
        else
          echo "Unsupported architecture: $arch" >&2; exit 2
        fi
        echo "Downloading $url ..."
        wget -N "$url" -O dms-latest.deb
        echo "Installing ..."
        sudo apt install ./dms-latest.deb -y --allow-downgrades
        echo "Cleaning up ..."
        rm -f dms-latest.deb || true
        echo "✅ Update complete."
    '''
    argv = ["bash", "-lc", update_script]
    await run_pty_ws(ws, argv, env=env, cwd=None, label="update")

@router.get("/peers/connected", response_model=ConnectedPeers)
def peers_connected(mgr: DMSManager = Depends(get_mgr)):
    """
    Returns the list of connected peers, normalized into JSON.
    Uses the existing DMSManager.view_peer_details() and parses stdout.
    """
    res = mgr.view_peer_details()
    if not res or res.get("status") != "success":
        # Propagate a helpful error but keep behavior pure (we don't change the module)
        raise HTTPException(status_code=503, detail=res.get("message", "Peer list unavailable"))

    stdout = res.get("message") or ""
    parsed = parse_connected_peers(stdout)
    peers_models = [ConnectedPeer(**p) for p in parsed]
    # If parsing failed, include raw so the UI can show the text
    return ConnectedPeers(count=len(peers_models), peers=peers_models, raw=None if peers_models else stdout)

@router.get("/status/combined", response_model=FullStatusCombined)
def status_combined(mgr: DMSManager = Depends(get_mgr)):
    """
    Combined resources + DMS status as JSON, plus a human-readable summary text
    (mirrors show_full_status without colors).
    """
    info = mgr.get_full_status_info()
    # Normalize DMS fields so dms_running is a proper bool, etc.
    dms_norm = normalize_dms_status(info)

    resources = ResourcesInfo(
        onboarding_status=info.get("onboarding_status", "Unknown"),
        free_resources=info.get("free_resources", "Unknown"),
        allocated_resources=info.get("allocated_resources", "Unknown"),
        onboarded_resources=info.get("onboarded_resources", "Unknown"),
    )
    dms = DmsStatus(**dms_norm)
    summary_text = build_full_status_summary({**info, **dms_norm})

    return FullStatusCombined(resources=resources, dms=dms, summary_text=summary_text)

@router.get("/logs", response_model=CommandResult)
def dms_logs(lines: int = 200):
    """
    Fetch recent DMS service logs via journalctl.
    """
    argv = ["sudo", "-n", "journalctl", "-u", "nunetdms", "-n", str(lines), "--no-pager", "--output=short-iso"]
    return _run_captured(argv, label="dms logs")

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
