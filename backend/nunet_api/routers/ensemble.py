import json
import subprocess
import logging
import re
import yaml
from fastapi import APIRouter, HTTPException, Depends, Query, Body, BackgroundTasks, Request
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
import time
from modules.ensemble_manager_v2 import EnsembleManagerV2
from modules.dms_utils import run_dms_command_with_passphrase, get_dms_status_info
from modules.path_constants import DMS_DEPLOYMENTS_DIR
from modules.dms_manager import DMSManager, _make_filelog, _request_allocation_logs
from modules.path_constants import ENSEMBLES_DIR
from modules.onboarding_manager import OnboardingManager
from ..schemas import (
    DeploymentsWebResponse, DeploymentWebItem,
    RunningListResponse, RunningItem,
    ManifestTextResponse, LogsTextResponse,
    DeploymentFileResponse,
    DeploymentInfoResponse,
    DeployRequest, DeployResponse,
    ShutdownResponse, TemplatesListItem, TemplatesListResponse,
    CopyRequest, CopyResponse, DownloadExamplesRequest, SimpleStatusResponse,
    AsyncDeploymentLogsResponse,
)

from modules.ensemble_utils import (
    load_ensemble_metadata, process_yaml_template,
    validate_form_data, save_deployment_instance, get_deployment_options
)

logger = logging.getLogger(__name__)

router = APIRouter()
logger = logging.getLogger(__name__)

# Replace any {{ ... }} placeholder with a scalar to make YAML parseable for counting nodes.
_JINJA_VAR_RE = re.compile(r"{{[^{}]*}}")


def _is_placeholder_peer(val: Any) -> bool:
    """
    Determine whether a peer value should be treated as a placeholder/dummy.

    We ignore:
      - None / non-strings (e.g., 0 after placeholder sanitization)
      - empty strings
      - Jinja placeholders that may remain quoted (e.g. "{{ peer_id }}")
      - "0" (common sanitized placeholder string)
      - "__DUMMY_PEER__" (used by rendering logic)
    """
    if val is None:
        return True
    if not isinstance(val, str):
        return True

    s = val.strip()
    if not s:
        return True
    if "{{" in s or "}}" in s:
        return True
    if s in ("0", "__DUMMY_PEER__"):
        return True
    return False


def _resolve_deploy_permission() -> Tuple[bool, Optional[str], str]:
    """
    Determine whether the active role is allowed to deploy ensembles.
    Returns (allowed, role_id, display_name).
    """
    mgr = OnboardingManager()
    allowed = mgr.role_allows("deploy")
    role_id = mgr.get_selected_role_id()
    profile = mgr.get_active_role_profile()
    label = profile.get("label") if isinstance(profile, dict) else None
    display = label or role_id or "current role"
    return allowed, role_id, display


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
            # Swallow - validation will catch if still required
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


def _read_allocations_from_disk(deployment_id: str) -> List[str]:
    """Return allocation directory names present on disk for this deployment."""
    base = DMS_DEPLOYMENTS_DIR / deployment_id
    try:
        if not base.exists() or not base.is_dir():
            return []
        return sorted(entry.name for entry in base.iterdir() if entry.is_dir())
    except Exception:
        return []


def _merge_alloc_names_with_disk_dirs(alloc_names: List[str], deployment_id: str) -> List[str]:
    """Reconcile manifest/DMS allocation labels with on-disk directory names under the deployment."""
    allocs = list(alloc_names)
    disk_allocs = _read_allocations_from_disk(deployment_id)
    if allocs and disk_allocs:
        disk_lower_map = {name.lower(): name for name in disk_allocs}
        disk_suffix_map: Dict[str, List[str]] = {}
        for name in disk_allocs:
            suffix = name.rsplit(".", 1)[-1].lower()
            disk_suffix_map.setdefault(suffix, []).append(name)

        def _to_disk(name: str) -> str:
            lowered = name.lower()
            if lowered in disk_lower_map:
                return disk_lower_map[lowered]
            candidates = disk_suffix_map.get(lowered)
            if candidates and len(candidates) == 1:
                return candidates[0]
            if "." in lowered:
                suffix = lowered.rsplit(".", 1)[-1]
                suffix_matches = disk_suffix_map.get(suffix)
                if suffix_matches and len(suffix_matches) == 1:
                    return suffix_matches[0]
            return name

        allocs = [_to_disk(name) for name in allocs]
    if not allocs:
        allocs = disk_allocs
    return allocs


def _parse_allocations_csv(allocations: str) -> List[str]:
    return [part.strip() for part in allocations.split(",") if part.strip()]


def _resolve_allocation_from_dashboard(
    deployment_id: str,
    requested_alloc: str | None,
    known_allocations: List[str],
) -> Tuple[Optional[str], List[str]]:
    """
    Resolve allocation using the same name list as GET .../info?logs=true (no second /info call).
    """
    if not known_allocations:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "missing_allocations",
                "message": (
                    "Pass `allocations` as a comma-separated list of names from "
                    "GET /ensemble/deployments/{id}/info?logs=true."
                ),
            },
        )

    allocs = _merge_alloc_names_with_disk_dirs(known_allocations, deployment_id)
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
    normalized = {alloc.lower(): alloc for alloc in allocs}

    if requested_key in normalized:
        return normalized[requested_key], allocs

    suffix_map: Dict[str, List[str]] = {}
    for alloc in allocs:
        suffix = alloc.rsplit(".", 1)[-1].lower()
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


def _validated_log_file_under_deployment(deployment_id: str, label: str, raw: str) -> Path:
    """Ensure stdout/stderr paths from the client stay under this deployment's DMS work directory."""
    if not raw or not str(raw).strip():
        raise HTTPException(
            status_code=400,
            detail={
                "error": "missing_log_path",
                "path": label,
                "message": f"Missing {label}. Use paths from GET /ensemble/deployments/{deployment_id}/info?logs=true.",
            },
        )
    try:
        p = Path(str(raw).strip()).expanduser().resolve()
    except OSError as exc:
        raise HTTPException(
            status_code=400,
            detail={"error": "invalid_log_path", "path": label, "message": str(exc)},
        ) from exc
    base = (DMS_DEPLOYMENTS_DIR / deployment_id).resolve()
    try:
        p.relative_to(base)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "invalid_log_path",
                "path": label,
                "message": f"{label} must be under {base}",
            },
        ) from exc
    return p


@router.get("/deployments", response_model=DeploymentsWebResponse)
def list_deployments(
    request: Request,
    status: Optional[List[str]] = Query(default=None),
    created_after: Optional[str] = Query(default=None),
    limit: Optional[int] = Query(default=None, ge=1),
    offset: Optional[int] = Query(default=None, ge=0),
    sort: Optional[str] = Query(default=None),
    filter: Optional[str] = Query(default=None),
    include_manifest: bool = Query(default=False),
    status_ordered: bool = Query(default=False),
    mgr: EnsembleManagerV2 = Depends(get_mgr),
):
    if created_after is None:
        created_after = request.query_params.get("created-after")

    res = mgr.get_deployments_for_web(
        statuses=status,
        created_after=created_after,
        limit=limit,
        offset=offset,
        sort=sort,
        metadata_filter=filter,
        include_manifest=include_manifest,
        status_ordered=status_ordered,
        refresh_status=False,
    )
    if res.get("status") != "success":
        raise HTTPException(status_code=500, detail=res.get("message", "Failed to get deployments"))

    items: List[DeploymentWebItem] = []
    for d in res.get("deployments", []):
        ts = str(d.get("timestamp"))
        # ensure isoformat
        if isinstance(ts, datetime):
            ts = ts.isoformat()
        ensemble_file_value = d.get("ensemble_file", "")
        if ensemble_file_value is None:
            ensemble_file_value = ""
        items.append(DeploymentWebItem(
            id=d.get("id", ""),
            status=d.get("status", ""),
            type=d.get("type", ""),
            timestamp=str(ts),
            ensemble_file=str(ensemble_file_value),
            ensemble_file_name=d.get("ensemble_file_name"),
            ensemble_file_path=d.get("ensemble_file_path"),
            ensemble_file_relative=d.get("ensemble_file_relative"),
            ensemble_file_exists=d.get("ensemble_file_exists"),
        ))

    return DeploymentsWebResponse(
        status=res["status"],
        deployments=items,
        count=res.get("count", len(items)),
        total=res.get("total"),
        has_more=res.get("has_more"),
        next_offset=res.get("next_offset"),
    )


@router.get("/deployments/{deployment_id}/file", response_model=DeploymentFileResponse)
def deployment_file_content(deployment_id: str, mgr: EnsembleManagerV2 = Depends(get_mgr)):
    res = mgr.get_deployment_file_content(deployment_id)
    if res.get("status") != "success":
        detail_message = res.get("message", "Deployment file is unavailable")
        detail = {"message": detail_message}
        if res.get("file_name"):
            detail["file_name"] = res["file_name"]
        if "candidates" in res:
            detail["candidates"] = res["candidates"]
        status_code = 404 if res.get("exists") is False else 500
        raise HTTPException(status_code=status_code, detail=detail)

    return DeploymentFileResponse(
        status="success",
        file_name=res.get("file_name"),
        file_path=res.get("file_path"),
        file_relative_path=res.get("file_relative_path"),
        content=res.get("content"),
        exists=res.get("exists", True),
        message=res.get("message"),
    )


@router.get(
    "/deployments/{deployment_id}/info",
    response_model=DeploymentInfoResponse,
    response_model_exclude_none=True,
)
def deployment_info(
    deployment_id: str,
    usage: bool = Query(default=False, description="Include resource usage statistics"),
    logs: bool = Query(default=False, description="Include log file paths"),
    allocations: Optional[List[str]] = Query(
        default=None,
        description="Optional allocation names to include logs for (requires logs=true).",
    ),
    mgr: EnsembleManagerV2 = Depends(get_mgr),
):
    """
    Consolidated deployment information endpoint backed by DMS:
      /dms/node/deployment/info

    This is intended to replace multiple frontend calls (status, manifest, allocations)
    with a single request.
    """
    cmd: List[str] = ["nunet", "-c", "dms", "actor", "cmd"]
    # The info behavior can take longer when usage is requested; bump actor timeout.
    # Note: DMS --logs has proven slow/unreliable in practice; the backend computes log paths
    # directly from the local DMS work directory instead of invoking DMS for them.
    if usage:
        cmd.extend(["--timeout", "180s"])
        subprocess_timeout = 210
    else:
        subprocess_timeout = 60

    cmd.extend(["/dms/node/deployment/info", "--id", deployment_id])
    if usage:
        cmd.append("--usage")

    try:
        cp = run_dms_command_with_passphrase(
            cmd,
            capture_output=True,
            text=True,
            check=False,
            timeout=subprocess_timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise HTTPException(
            status_code=504,
            detail={
                "error": "dms_timeout",
                "message": f"DMS deployment info request timed out after {subprocess_timeout}s",
            },
        ) from exc
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=500,
            detail={"error": "nunet_not_found", "message": "nunet CLI not available"},
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={"error": "dms_command_failed", "message": str(exc)},
        ) from exc

    stdout = (cp.stdout or "").strip()
    stderr = (cp.stderr or "").strip()
    if cp.returncode != 0:
        message = stderr or stdout or f"Command failed with return code {cp.returncode}"
        raise HTTPException(
            status_code=502,
            detail={
                "error": "deployment_info_failed",
                "message": message,
                "returncode": cp.returncode,
            },
        )

    try:
        data = json.loads(stdout) if stdout else {}
    except json.JSONDecodeError as je:
        raise HTTPException(
            status_code=502,
            detail={"error": "invalid_json", "message": f"nunet returned invalid JSON: {je}"},
        ) from je

    if not isinstance(data, dict):
        raise HTTPException(
            status_code=502,
            detail={"error": "unexpected_payload", "message": "nunet returned non-object JSON"},
        )

    raw_status = data.get("status")
    status_lower = str(raw_status or "").strip().lower()
    if status_lower in {"completed", "complete", "finished", "success", "done"}:
        deployment_status = "completed"
        status_message = "Deployment completed successfully"
    elif status_lower in {"failed", "error", "cancelled", "canceled"}:
        deployment_status = "failed"
        status_message = "Deployment failed"
    elif status_lower:
        deployment_status = "running"
        status_message = f"Deployment is currently {status_lower}"
    else:
        deployment_status = "unknown"
        status_message = "Deployment status is unknown"

    # Match the existing /manifest/raw response structure expected by the UI (manifest nested under "manifest").
    manifest_payload: Dict[str, Any] = {"manifest": data.get("manifest")}
    if isinstance(manifest_payload.get("manifest"), dict):
        try:
            manifest_payload = mgr.enrich_manifest_payload(deployment_id, manifest_payload)
        except Exception as exc:
            meta = manifest_payload.setdefault("meta", {})
            meta["proxy_enrichment_error"] = str(exc)
        try:
            manifest_payload["dms_status"] = get_dms_status_info()
        except Exception:
            pass

    allocs: List[str] = []
    manifest_obj = manifest_payload.get("manifest")
    if isinstance(manifest_obj, dict):
        manifest_allocations = manifest_obj.get("allocations")
        if isinstance(manifest_allocations, dict):
            allocs = [str(k) for k in manifest_allocations.keys()]

    def _alloc_name_from(candidate: Any) -> Optional[str]:
        if not isinstance(candidate, str):
            return None
        s = candidate.strip()
        if not s:
            return None
        # DMS commonly prefixes allocation_id as "<deployment_id>_<allocation_name>".
        if "_" in s:
            return s.split("_", 1)[1]
        return s

    def _normalize_alloc_map(raw: Any) -> Dict[str, Any]:
        """
        Normalize DMS maps keyed by allocation_id into maps keyed by allocation_name
        (e.g. "<dep>_node1.alloc1" -> "node1.alloc1").
        """
        out: Dict[str, Any] = {}
        if not isinstance(raw, dict):
            return out
        for key, value in raw.items():
            alloc_id = value.get("allocation_id") if isinstance(value, dict) else None
            name = _alloc_name_from(alloc_id) or _alloc_name_from(key)
            if name:
                out[name] = value
        return out

    runtime_allocations = data.get("allocations")
    allocations_by_name = _normalize_alloc_map(runtime_allocations)
    # Ensure allocations_info contains at least the manifest-provided allocations so optional
    # payloads (usage/logs) can attach even if DMS runtime "allocations" is missing/empty.
    for alloc_name in allocs:
        allocations_by_name.setdefault(str(alloc_name), {})

    # Some DMS builds return usage/logs as separate maps; merge into allocations_info
    # for a stable frontend contract.
    usage_by_name = _normalize_alloc_map(data.get("usage")) if usage else {}
    logs_by_name = _normalize_alloc_map(data.get("logs")) if logs else {}
    for alloc_name, info in allocations_by_name.items():
        if isinstance(info, dict):
            if alloc_name in usage_by_name and "resource_usage" not in info:
                info["resource_usage"] = usage_by_name[alloc_name]
            if alloc_name in logs_by_name and "logs" not in info:
                info["logs"] = logs_by_name[alloc_name]

    # Compute log paths from the local filesystem for performance/reliability.
    fs_logs_by_name: Dict[str, Any] = {}
    if logs:
        requested_allocs = [
            str(name).strip()
            for name in (allocations or [])
            if str(name).strip()
        ]
        requested_set = {name.lower() for name in requested_allocs} if requested_allocs else None

        disk_allocs = _read_allocations_from_disk(deployment_id)
        disk_lower_map = {name.lower(): name for name in disk_allocs}

        def _disk_name_for(name: str) -> str:
            return disk_lower_map.get(name.lower(), name)

        for alloc_name, info in allocations_by_name.items():
            if requested_set is not None and alloc_name.lower() not in requested_set:
                continue

            disk_name = _disk_name_for(alloc_name)
            alloc_dir = DMS_DEPLOYMENTS_DIR / deployment_id / disk_name
            # Always return the expected paths for UX, even if the directory hasn't been created yet.
            # Use *_exists fields to indicate whether the paths are currently present on disk.
            stdout_path = alloc_dir / "stdout.log"
            stderr_path = alloc_dir / "stderr.log"
            dir_exists = alloc_dir.exists() and alloc_dir.is_dir()
            entry: Dict[str, Any] = {
                "stdout_path": str(stdout_path),
                "stderr_path": str(stderr_path),
                "logs_written_to": str(alloc_dir),
                "dir_exists": dir_exists,
                "stdout_exists": stdout_path.exists() if dir_exists else False,
                "stderr_exists": stderr_path.exists() if dir_exists else False,
            }
            if not dir_exists:
                entry["error"] = f"logs directory not found for allocation {alloc_name}"
            fs_logs_by_name[alloc_name] = entry

            # Prefer filesystem-derived paths over DMS-provided error payloads.
            if isinstance(info, dict):
                current = info.get("logs")
                if not isinstance(current, dict):
                    info["logs"] = fs_logs_by_name[alloc_name]
                else:
                    has_paths = "stdout_path" in current or "stderr_path" in current
                    if not has_paths:
                        info["logs"] = fs_logs_by_name[alloc_name]

    resp: Dict[str, Any] = {
        "id": str(data.get("id") or deployment_id),
        "error": data.get("error"),
        "raw_status": raw_status,
        "status": {
            "status": "success",
            "deployment_status": deployment_status,
            "message": status_message,
        },
        "manifest": manifest_payload,
        "allocations": allocs,
        "allocations_info": allocations_by_name,
    }

    if usage and usage_by_name:
        resp["usage"] = usage_by_name
    if logs and (logs_by_name or fs_logs_by_name):
        # Prefer filesystem-derived logs map; keep DMS logs map if present.
        resp["logs"] = fs_logs_by_name or logs_by_name

    return resp


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


def _extract_log_content(entry: dict | None) -> str:
    if not entry:
        return ""
    content = entry.get("content")
    if content:
        return content
    # Suppress error metadata from reaching the UI; callers will fall back to placeholders.
    # For empty files, keep empty string so UI shows placeholder.
    return ""


def _extract_dms_content(bundle: dict | None) -> str:
    if not bundle:
        return ""
    stdout = (bundle.get("stdout") or "").strip()
    if stdout:
        return stdout
    stderr = (bundle.get("stderr") or "").strip()
    if stderr:
        rc = bundle.get("returncode")
        prefix = "[stderr]\n" if rc not in (0, None) else ""
        return f"{prefix}{stderr}"
    return ""


def _prefer_filtered_dms(
    fallback: dict | None,
    candidate: dict | None,
) -> dict | None:
    if candidate is not None:
        return candidate
    return fallback

@router.post("/deployments/{deployment_id}/logs/request", response_model=SimpleStatusResponse)
def request_deployment_logs(
    deployment_id: str,
    allocation: str | None = Query(
        default=None,
        description="Allocation name (from GET .../info?logs=true); required when multiple allocations exist",
    ),
    allocations: str = Query(
        ...,
        min_length=1,
        description="Comma-separated allocation names from GET .../info?logs=true",
    ),
    wait: bool = Query(
        default=False,
        description="Wait for DMS to finish the log request",
    ),
    background_tasks: BackgroundTasks = None,
    mgr: EnsembleManagerV2 = Depends(get_mgr),
):
    known = _parse_allocations_csv(allocations)
    selected_alloc, allocs = _resolve_allocation_from_dashboard(deployment_id, allocation, known)
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

    if not wait:
        if background_tasks is None:
            return SimpleStatusResponse(
                status="warning",
                message="Background task support unavailable; retry with wait=true.",
            )
        background_tasks.add_task(
            _run_log_request_background,
            cmd,
        )
        return SimpleStatusResponse(
            status="success",
            message=f"Log request queued for allocation {selected_alloc}.",
        )

    max_attempts = 2
    timeout_sec = 30
    last_error = None
    result = None
    timed_out = False
    for attempt in range(1, max_attempts + 1):
        try:
            result = run_dms_command_with_passphrase(
                cmd,
                capture_output=True,
                text=True,
                check=False,
                timeout=timeout_sec,
            )
        except subprocess.TimeoutExpired as exc:
            last_error = f"log request timed out: {exc}"
        except FileNotFoundError as exc:
            raise HTTPException(
                status_code=500,
                detail={"error": "nunet_not_found", "message": "nunet CLI not available"},
            ) from exc
        except Exception as exc:
            last_error = str(exc)
        else:
            stdout = (result.stdout or "").strip()
            stderr = (result.stderr or "").strip()
            if result.returncode == 0:
                break
            error_text = f"{stderr}\n{stdout}".lower()
            last_error = stderr or stdout or f"Command failed with return code {result.returncode}"
            if "request timeout" in error_text or "status 408" in error_text:
                timed_out = True
            if not timed_out:
                break
        if attempt < max_attempts:
            time.sleep(2)

    if not result or result.returncode != 0:
        if timed_out:
            return SimpleStatusResponse(
                status="warning",
                message=(
                    "Log request timed out; logs may appear after a short delay. "
                    "Try refreshing the logs view."
                ),
            )
        raise HTTPException(
            status_code=502,
            detail={"error": "log_request_failed", "message": last_error or "Failed to request logs."},
        )

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


def _run_log_request_background(cmd: list[str]) -> None:
    try:
        run_dms_command_with_passphrase(
            cmd,
            capture_output=True,
            text=True,
            check=False,
            timeout=90,
        )
    except Exception as exc:
        logger.warning("Background log request failed: %s", exc)


def _build_async_logs_cmd(
    subpath: str,
    deployment_id: str,
    allocation: str,
    *,
    follow: bool = False,
) -> list[str]:
    cmd = [
        "nunet",
        "-c",
        "dms",
        "actor",
        "cmd",
        f"/dms/node/deployment/logs/{subpath}",
    ]
    if follow:
        cmd.append("--follow")
    cmd.extend(["--id", deployment_id, "--allocation", allocation])
    return cmd


def _parse_async_logs_payload(stdout: str) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    if not stdout:
        return payload
    try:
        parsed = json.loads(stdout)
    except json.JSONDecodeError:
        return payload
    if not isinstance(parsed, dict):
        return payload

    logs_written_to = parsed.get("LogsWrittenTo") or parsed.get("logs_written_to")
    fetch_status = parsed.get("Status") or parsed.get("status")
    bytes_written = parsed.get("BytesWritten")
    follow = parsed.get("Follow")
    follow_interval = parsed.get("FollowInterval") or parsed.get("follow_interval")
    error = parsed.get("Error") or parsed.get("error")

    if logs_written_to is not None:
        payload["logs_written_to"] = str(logs_written_to)
    if fetch_status is not None:
        payload["fetch_status"] = str(fetch_status)
    if bytes_written is not None:
        try:
            payload["bytes_written"] = int(bytes_written)
        except (TypeError, ValueError):
            pass
    if follow is not None:
        payload["follow"] = bool(follow)
    if follow_interval is not None:
        payload["follow_interval"] = str(follow_interval)
    if error is not None and str(error).strip():
        payload["error"] = str(error)
    return payload


def _run_async_logs_command(cmd: list[str], *, timeout: int = 30) -> AsyncDeploymentLogsResponse:
    try:
        result = run_dms_command_with_passphrase(
            cmd,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=500,
            detail={"error": "nunet_not_found", "message": "nunet CLI not available"},
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise HTTPException(
            status_code=504,
            detail={"error": "async_log_request_timeout", "message": f"Async log command timed out: {exc}"},
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail={"error": "async_log_request_failed", "message": str(exc)},
        ) from exc

    stdout = (result.stdout or "").strip()
    stderr = (result.stderr or "").strip()
    if result.returncode != 0:
        raise HTTPException(
            status_code=502,
            detail={
                "error": "async_log_request_failed",
                "message": stderr or stdout or f"Command failed with return code {result.returncode}",
            },
        )

    parsed = _parse_async_logs_payload(stdout)
    message = stdout or stderr or "Async log command completed"
    if parsed.get("error"):
        message = parsed["error"]
    elif parsed.get("fetch_status"):
        message = f"Async log fetch status: {parsed['fetch_status']}"

    return AsyncDeploymentLogsResponse(
        status="success",
        message=message,
        **parsed,
    )


def _resolve_async_logs_allocation(
    deployment_id: str,
    allocation: str | None,
    allocations: str,
) -> str:
    known = _parse_allocations_csv(allocations)
    selected_alloc, allocs = _resolve_allocation_from_dashboard(deployment_id, allocation, known)
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
    return selected_alloc


@router.post(
    "/deployments/{deployment_id}/logs/async/start",
    response_model=AsyncDeploymentLogsResponse,
)
def request_deployment_logs_async(
    deployment_id: str,
    allocation: str | None = Query(
        default=None,
        description="Allocation name (from GET .../info?logs=true); required when multiple allocations exist",
    ),
    allocations: str = Query(
        ...,
        min_length=1,
        description="Comma-separated allocation names from GET .../info?logs=true",
    ),
):
    selected_alloc = _resolve_async_logs_allocation(deployment_id, allocation, allocations)
    cmd = _build_async_logs_cmd("async", deployment_id, selected_alloc, follow=True)
    return _run_async_logs_command(cmd)


@router.get(
    "/deployments/{deployment_id}/logs/async/status",
    response_model=AsyncDeploymentLogsResponse,
)
def get_deployment_logs_async_status(
    deployment_id: str,
    allocation: str | None = Query(
        default=None,
        description="Allocation name (from GET .../info?logs=true); required when multiple allocations exist",
    ),
    allocations: str = Query(
        ...,
        min_length=1,
        description="Comma-separated allocation names from GET .../info?logs=true",
    ),
):
    selected_alloc = _resolve_async_logs_allocation(deployment_id, allocation, allocations)
    cmd = _build_async_logs_cmd("async/status", deployment_id, selected_alloc)
    return _run_async_logs_command(cmd)


@router.post(
    "/deployments/{deployment_id}/logs/async/stop",
    response_model=AsyncDeploymentLogsResponse,
)
def stop_deployment_logs_async(
    deployment_id: str,
    allocation: str | None = Query(
        default=None,
        description="Allocation name (from GET .../info?logs=true); required when multiple allocations exist",
    ),
    allocations: str = Query(
        ...,
        min_length=1,
        description="Comma-separated allocation names from GET .../info?logs=true",
    ),
):
    selected_alloc = _resolve_async_logs_allocation(deployment_id, allocation, allocations)
    cmd = _build_async_logs_cmd("async/stop", deployment_id, selected_alloc)
    return _run_async_logs_command(cmd)


@router.get("/deployments/{deployment_id}/logs", response_model=LogsTextResponse)
def deployment_logs_text(
    deployment_id: str,
    allocation: str | None = Query(default=None, description="Allocation name from GET .../info?logs=true"),
    allocations: Optional[str] = Query(
        default=None,
        description="Comma-separated allocation names from GET .../info?logs=true (required when include_alloc=true)",
    ),
    stdout_path: Optional[str] = Query(
        default=None,
        description="stdout.log path from allocations_info[allocation].logs (required when include_alloc=true)",
    ),
    stderr_path: Optional[str] = Query(
        default=None,
        description="stderr.log path from allocations_info[allocation].logs (required when include_alloc=true)",
    ),
    dms_query: str | None = Query(default=None, description="Optional jq filter for DMS logs"),
    refresh_alloc: bool = Query(default=True, description="Refresh allocation logs via DMS before reading files"),
    dms_lines: int = Query(
        default=2000,
        ge=1,
        le=10000,
        description="Number of DMS log lines to scan for filtered output",
    ),
    dms_view: str = Query(
        default="compact",
        description="DMS log view: compact, folded, expanded, map, raw",
    ),
    include_alloc: bool = Query(
        default=True,
        description="Include allocation stdout/stderr logs in response",
    ),
):
    """
    Allocation logs require paths from the single GET .../info?logs=true call (no second /info).
    """
    selected_alloc: Optional[str] = None
    alloc_dir: Optional[Path] = None
    stdout_p: Optional[Path] = None
    stderr_p: Optional[Path] = None

    if include_alloc:
        if not allocations or not str(allocations).strip():
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "missing_allocations",
                    "message": "Pass `allocations` (comma-separated) from GET /ensemble/deployments/{id}/info?logs=true.",
                },
            )
        if not stdout_path or not stderr_path:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "missing_log_paths",
                    "message": "Pass `stdout_path` and `stderr_path` from allocations_info[...].logs on GET .../info?logs=true.",
                },
            )
        known = _parse_allocations_csv(allocations)
        if not known:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "missing_allocations",
                    "message": "`allocations` must list at least one allocation name.",
                },
            )
        selected_alloc, allocs = _resolve_allocation_from_dashboard(deployment_id, allocation, known)
        if not selected_alloc:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "allocation_required",
                    "allocations": allocs or known,
                    "message": "Could not resolve allocation for logs.",
                },
            )
        stdout_p = _validated_log_file_under_deployment(deployment_id, "stdout_path", stdout_path)
        stderr_p = _validated_log_file_under_deployment(deployment_id, "stderr_path", stderr_path)
        alloc_dir = stdout_p.parent

        if refresh_alloc:
            ok, msg = _request_allocation_logs(deployment_id, selected_alloc)
            if not ok:
                logger.warning(
                    "DMS log refresh failed for %s/%s: %s",
                    deployment_id,
                    selected_alloc,
                    msg or "no message",
                )

    try:
        dm = DMSManager()
        alloc_lines_limit = 400
        if include_alloc and selected_alloc and stdout_p is not None and stderr_p is not None:
            structured = {
                "status": "success",
                "message": "Structured logs fetched",
                "allocation": {
                    "dir": str(stdout_p.parent),
                    "stdout": _make_filelog(stdout_p, alloc_lines_limit),
                    "stderr": _make_filelog(stderr_p, alloc_lines_limit),
                },
                "dms_logs": None,
            }
        else:
            structured = dm.get_structured_logs(
                None,
                lines=alloc_lines_limit,
                refresh_alloc_logs=False,
                include_dms_logs=False,
            )
        filtered_dms = dm.get_filtered_dms_logs(
            deployment_id,
            query=dms_query,
            max_lines=dms_lines,
            view=dms_view,
        )
    except HTTPException:
        raise
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
    dms_bundle = _prefer_filtered_dms(structured.get("dms_logs"), filtered_dms)

    lines_out.append("")
    lines_out.append(_format_dms_section(dms_bundle))

    log_message = "\n".join(lines_out).strip()
    return LogsTextResponse(
        status=status_text,
        message=log_message,
        stdout=_extract_log_content(stdout_section),
        stderr=_extract_log_content(stderr_section),
        dms=_extract_dms_content(dms_bundle),
        allocation=structured.get("allocation"),
        dms_logs=dms_bundle,
    )


@router.post("/deployments", response_model=DeployResponse)
def deploy_ensemble(payload: DeployRequest, mgr: EnsembleManagerV2 = Depends(get_mgr)):
    allowed, role_id, role_display = _resolve_deploy_permission()
    if not allowed:
        OnboardingManager().append_log(
            "permissions",
            f"Blocked deployment attempt for role '{role_display}' ({role_id or 'unknown'}).",
        )
        raise HTTPException(
            status_code=403,
            detail=f"Role '{role_display}' is not permitted to deploy ensembles.",
        )
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


@router.delete("/deployments/{deployment_id}", response_model=SimpleStatusResponse)
def delete_deployment(deployment_id: str, mgr: EnsembleManagerV2 = Depends(get_mgr)):
    res = mgr.delete_deployment(deployment_id)
    if res.get("status") != "success":
        raise HTTPException(status_code=500, detail=res.get("message", "Delete failed"))
    return SimpleStatusResponse(status=res.get("status", "error"), message=res.get("message", ""))


@router.post("/deployments/prune", response_model=SimpleStatusResponse)
def prune_deployments(
    before: Optional[str] = Query(default=None),
    all: bool = Query(default=False),
    mgr: EnsembleManagerV2 = Depends(get_mgr),
):
    if not before and not all:
        raise HTTPException(status_code=400, detail="Provide before or all to prune deployments")
    res = mgr.prune_deployments(before=before, all=all)
    if res.get("status") != "success":
        raise HTTPException(status_code=500, detail=res.get("message", "Prune failed"))
    return SimpleStatusResponse(status=res.get("status", "error"), message=res.get("message", ""))


@router.get("/templates", response_model=TemplatesListResponse)
def list_templates(mgr: EnsembleManagerV2 = Depends(get_mgr)):
    items = mgr.get_ensemble_files()
    out: List[TemplatesListItem] = []
    for idx, path in items:
        try:
            rel = path.relative_to(mgr.base_dir)
        except Exception:
            rel = path.name
        category = rel.parts[0] if isinstance(rel, Path) and len(rel.parts) > 1 else "root"
        out.append(
            TemplatesListItem(
                index=idx,
                name=path.name,
                path=str(path),
                relative_path=str(rel),
                category=category,
            )
        )
    return TemplatesListResponse(items=out)


@router.post("/templates/copy", response_model=CopyResponse)
def copy_template(payload: CopyRequest, mgr: EnsembleManagerV2 = Depends(get_mgr)):
    src = _resolve_path(mgr, payload.source)
    dst = _resolve_path(mgr, payload.dest)
    res = mgr.copy_ensemble(src, dst)
    return CopyResponse(status=res.get("status", "error"), message=res.get("message", ""))


@router.get("/templates/categories", response_model=List[str])
def list_template_categories() -> List[str]:
    """List top-level ensemble folders (including root)."""
    categories = {"root"}
    try:
        for entry in ENSEMBLES_DIR.iterdir():
            if entry.is_dir():
                categories.add(entry.name)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Unable to list ensemble categories: %s", exc)
    return sorted(categories)


@router.post("/examples/download", response_model=SimpleStatusResponse)
def download_examples(payload: DownloadExamplesRequest, mgr: EnsembleManagerV2 = Depends(get_mgr)):
    res = mgr.download_example_ensembles(
        repo=payload.repo or mgr.repo,
        branch=payload.branch,
        source_dir=payload.source_dir or mgr.source_dir,
        target_dir=Path(payload.target_dir).expanduser() if payload.target_dir else None,
    )
    return SimpleStatusResponse(status=res.get("status", "error"), message=res.get("message", ""))


@router.get("/templates/yamls", response_model=dict)
def list_yaml_templates(
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    page_size: int = Query(10, ge=1, le=100, description="Items per page"),
    with_content: bool = Query(False, description="Include file contents inline"),
    mgr: EnsembleManagerV2 = Depends(get_mgr),
):
    """
    List YAML ensemble files (for deployment) under ~/ensembles.
    Returned paths feed directly into the standard deployment endpoints.
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


@router.get("/templates/nodes-count", response_model=dict)
def template_nodes_count(
    template_path: str = Query(..., description="Path under ~/ensembles, e.g. rare-evo/floppybird.yaml"),
    mgr: EnsembleManagerV2 = Depends(get_mgr),
):
    """
    Parse the selected YAML ensemble template and return the number of nodes.
    This uses PyYAML on the backend, called from Step 2 in the UI.

    Note: Many templates contain unquoted {{ ... }} placeholders, which are not valid YAML.
    For the purpose of counting nodes, we replace those placeholders with a dummy scalar (0)
    to make the YAML parseable.
    """
    tpl = _resolve_template_in_base(mgr, template_path)
    try:
        yaml_text = tpl.read_text(encoding="utf-8")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Unable to read YAML file: {exc}") from exc

    yaml_text_for_parse = _JINJA_VAR_RE.sub("0", yaml_text)

    try:
        doc = yaml.safe_load(yaml_text_for_parse) or {}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid YAML: {exc}") from exc

    nodes_list: List[str] = []
    node_peers: Dict[str, str] = {}

    if isinstance(doc, dict):
        nodes = doc.get("nodes")
        if isinstance(nodes, dict):
            nodes_list = [str(k) for k in nodes.keys()]
            for node_id, node_cfg in nodes.items():
                if isinstance(node_cfg, dict):
                    peer_val = node_cfg.get("peer")
                    if isinstance(peer_val, str) and not _is_placeholder_peer(peer_val):
                        node_peers[str(node_id)] = peer_val.strip()
        elif isinstance(nodes, list):
            nodes_list = [str(i) for i in range(len(nodes))]
            for idx, node_cfg in enumerate(nodes):
                if isinstance(node_cfg, dict):
                    peer_val = node_cfg.get("peer")
                    if isinstance(peer_val, str) and not _is_placeholder_peer(peer_val):
                        node_peers[str(idx)] = peer_val.strip()

    nodes_count = len(nodes_list)

    try:
        rel = str(tpl.relative_to(mgr.base_dir))
    except Exception:
        rel = str(tpl)

    return {
        "status": "success",
        "template_path": rel,
        "nodes_count": nodes_count,
        "nodes": nodes_list,
        "node_peers": node_peers,
    }


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

    # Validate after we've adjusted for the type
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
        "save_instance": True,
        "peer_ids": ["12D3KooW...", None, "12D3KooX..."]  # optional for targeted multi-node (None = undecided)
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

    # peer_ids may include None to represent "undecided".
    peer_ids_raw = payload.get("peer_ids")
    peer_ids: Optional[List[Optional[str]]] = None
    if isinstance(peer_ids_raw, list) and all(isinstance(x, str) or x is None for x in peer_ids_raw):
        cleaned: List[Optional[str]] = []
        for x in peer_ids_raw:
            if isinstance(x, str):
                v = x.strip()
                cleaned.append(v if v else None)
            else:
                cleaned.append(None)
        peer_ids = cleaned

    # Prepare values per deployment type
    if deployment_type == "targeted":
        values = dict(values_in)

        if peer_ids is not None:
            # Enforce "must target at least one node"
            if not any(p for p in peer_ids):
                raise HTTPException(status_code=400, detail="At least one node must be targeted (select a peer).")

            # Ensure templates referencing peer_id still render, even though we will override per-node peers later.
            first_targeted_peer = next((p for p in peer_ids if p), None)
            values.setdefault("peer_id", first_targeted_peer or "__DUMMY_PEER__")

            # Pass peer_ids through to process_yaml_template (API-level control, not a template/YAML key).
            values["peer_ids"] = peer_ids

            # Validate peer_ids length matches nodes count (best-effort).
            try:
                raw_text = tpl.read_text(encoding="utf-8")
                sanitized = _JINJA_VAR_RE.sub("0", raw_text)
                doc = yaml.safe_load(sanitized) or {}
                nodes_list: List[str] = []
                if isinstance(doc, dict):
                    nodes = doc.get("nodes")
                    if isinstance(nodes, dict):
                        nodes_list = [str(k) for k in nodes.keys()]
                    elif isinstance(nodes, list):
                        nodes_list = [str(i) for i in range(len(nodes))]
                nodes_count = len(nodes_list)
                if nodes_count > 0 and len(peer_ids) != nodes_count:
                    raise HTTPException(
                        status_code=400,
                        detail=f"peer_ids length ({len(peer_ids)}) must match nodes count ({nodes_count})",
                    )
            except HTTPException:
                raise
            except Exception as exc:
                logger.warning("Unable to validate peer_ids length vs nodes count for %s: %s", tpl, exc)

        else:
            # Legacy behavior: a single peer_id required
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
