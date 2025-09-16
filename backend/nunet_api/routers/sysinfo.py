# nunet_api/app/routers/sysinfo.py
from fastapi import APIRouter, Depends, HTTPException, Query
from ..schemas import SshStatus
from ..adapters import parse_ssh_status
from modules.utils import get_local_ip, get_public_ip, get_appliance_version, get_ssh_status
import subprocess, shutil, json
from typing import Any, Dict, List

router = APIRouter()

@router.get("/local-ip", response_model=str)
def local_ip():
    return get_local_ip()

@router.get("/public-ip", response_model=str)
def public_ip():
    return get_public_ip()

@router.get("/appliance-version", response_model=str)
def appliance_version():
    return get_appliance_version()

@router.get("/ssh-status", response_model=SshStatus)
def ssh_status():
    return SshStatus(**parse_ssh_status(get_ssh_status()))

@router.get("/docker/containers", response_model=dict)
def docker_containers(include_all: bool = Query(False, alias="all", description="Include stopped containers (-a)")):
    """
    List Docker containers with key fields (names, images, status, etc.).
    - If Docker isn't installed or accessible, returns an error.
    - By default returns *running* containers (like `docker ps`).
    - Pass `?all=true` to include non-running containers (like `docker ps -a`).
    """
    docker_path = shutil.which("docker")
    if not docker_path:
        # Optionally: look for podman-docker wrapper here
        raise HTTPException(status_code=503, detail="docker not found in PATH")

    base_cmd = [docker_path, "ps", "--no-trunc"]
    if include_all:
        base_cmd.append("-a")

    # First try: JSON-per-line output (Docker Go-template: {{json .}})
    try:
        result = subprocess.run(
            base_cmd + ["--format", "{{json .}}"],
            capture_output=True, text=True, check=True
        )
    except subprocess.CalledProcessError as e:
        err = (e.stderr or e.stdout or str(e)).strip()
        # Common daemon permission error (e.g., user not in `docker` group)
        if "permission denied" in err.lower():
            raise HTTPException(status_code=403, detail=err)
        raise HTTPException(status_code=500, detail=err)

    lines = [ln for ln in (result.stdout or "").splitlines() if ln.strip()]
    containers: List[Dict[str, Any]] = []

    for ln in lines:
        try:
            obj = json.loads(ln)
            containers.append({
                "name": obj.get("Names"),
                "image": obj.get("Image"),
                "running_for": obj.get("RunningFor"),
            })
        except json.JSONDecodeError:
            # We'll fall back to TSV parsing below if nothing parsed
            pass

    # Fallback: parse a tab-separated format if JSON-per-line wasn't supported
    if not containers:
        try:
            result_tsv = subprocess.run(
                base_cmd + ["--format", "{{.ID}}\t{{.Names}}\t{{.Image}}\t{{.Status}}"],
                capture_output=True, text=True, check=True
            )
            for row in (result_tsv.stdout or "").splitlines():
                parts = row.split("\t")
                if len(parts) >= 4:
                    containers.append({
                        "id": parts[0],
                        "name": parts[1],
                        "image": parts[2],
                        "status": parts[3],
                    })
        except subprocess.CalledProcessError as e:
            err = (e.stderr or e.stdout or str(e)).strip()
            if "permission denied" in err.lower():
                raise HTTPException(status_code=403, detail=err)
            raise HTTPException(status_code=500, detail=err)

    return {"count": len(containers), "containers": containers}
