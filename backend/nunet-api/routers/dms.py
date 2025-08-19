# nunet_api/app/routers/dms.py
from fastapi import APIRouter, HTTPException, Depends, WebSocket
import os
from ..schemas import (
    InstallStatus, DmsStatus, CommandResult, PeerInfo, ResourcesInfo,ConnectedPeers, ConnectedPeer, FullStatusCombined
)
from ..adapters import normalize_dms_status, parse_connected_peers, build_full_status_summary
from pathlib import Path
import json, subprocess
from ..utils.pty_bridge import run_pty_ws
from modules.dms_manager import DMSManager
from modules.dms_utils import get_dms_status_info, get_dms_resource_info

router = APIRouter()

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
def stop(mgr: DMSManager = Depends(get_mgr)):
    return CommandResult(**mgr.stop_dms())

@router.post("/enable", response_model=CommandResult)
def enable(mgr: DMSManager = Depends(get_mgr)):
    return CommandResult(**mgr.enable_dms())

@router.post("/disable", response_model=CommandResult)
def disable(mgr: DMSManager = Depends(get_mgr)):
    return CommandResult(**mgr.disable_dms())

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
def init(mgr: DMSManager = Depends(get_mgr)):
    return CommandResult(**mgr.initialize_dms())

@router.post("/update", response_model=CommandResult)
def update(mgr: DMSManager = Depends(get_mgr)):
    return CommandResult(**mgr.update_dms())



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

@router.websocket("/ws/onboard")
async def ws_dms_onboard(ws: WebSocket):
    """
    Run the interactive onboarding (if it prompts) via PTY.
    """
    await ws.accept()
    env = os.environ.copy()
    dms_pw = _get_dms_passphrase()
    if dms_pw:
        env["DMS_PASSPHRASE"] = dms_pw

    mgr = DMSManager()
    script_path = (mgr.scripts_dir / "onboard-max.sh")
    if not script_path.exists():
        await ws.send_json({"type": "error", "message": f"Script missing: {script_path}"})
        await ws.close(code=4404)
        return

    argv = [str(script_path)]
    await run_pty_ws(ws, argv, env=env, cwd=None, label="onboard")

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