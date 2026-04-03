# nunet_api/app/routers/sysinfo.py
from pathlib import Path
from fastapi import APIRouter, HTTPException, Query, Request, Response
from ..schemas import (
    CommandResult,
    EnvironmentStatus,
    SshStatus,
    TelemetryPluginConfig,
    TelemetryPluginConfigUpdate,
    TelemetryLocalMetricsResponse,
    TelemetryLocalMetricPoint,
    TelemetryPluginStatus,
)
from ..adapters import parse_ssh_status
from modules.utils import (
    get_environment_status,
    get_appliance_version,
    get_local_ip,
    get_public_ip,
    get_ssh_status,
    get_appliance_updates,
    trigger_appliance_update,
    trigger_plugin_sync,
    trigger_telemetry_plugin_uninstall,
)
from modules.dms_manager import DMSManager
import subprocess
import shutil
import json
import time
import math
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

router = APIRouter()

_TELEMETRY_PLUGIN_ID = "telemetry-exporter"
_TELEMETRY_CONFIG_PATH = Path("/home/ubuntu/nunet/appliance/plugins/telemetry-exporter/config.json")
_TELEMETRY_STATE_PATH = Path("/var/lib/nunet-appliance/plugins/telemetry-exporter/state.json")
_TELEMETRY_DEFAULTS = {
    "enabled": False,
    "remote_enabled": False,
    "local_enabled": False,
    "dcgm_exporter_enabled": False,
    "grafana_enabled": False,
    "gateway_url": "https://telemetry.orgs.nunet.network",
    "telemetry_token": "",
    "generated_config_path": "/home/ubuntu/nunet/appliance/alloy/config.generated.alloy",
}


def _telemetry_status_hook_path() -> Optional[Path]:
    packaged = Path("/usr/lib/nunet-appliance-web/plugins/telemetry-exporter/hooks/status.sh")
    if packaged.is_file():
        return packaged
    repo = Path(__file__).resolve().parents[3] / "deploy" / "plugins" / "telemetry-exporter" / "hooks" / "status.sh"
    if repo.is_file():
        return repo
    return None


def _load_live_telemetry_status() -> Dict[str, Any]:
    hook_path = _telemetry_status_hook_path()
    if not hook_path:
        return {}
    try:
        proc = subprocess.run(
            [str(hook_path), str(_TELEMETRY_CONFIG_PATH)],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if proc.returncode != 0:
            return {}
        payload = json.loads((proc.stdout or "").strip() or "{}")
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _load_telemetry_config_raw() -> Dict[str, Any]:
    data = dict(_TELEMETRY_DEFAULTS)
    if _TELEMETRY_CONFIG_PATH.is_file():
        try:
            loaded = json.loads(_TELEMETRY_CONFIG_PATH.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                data.update(loaded)
        except (json.JSONDecodeError, OSError):
            pass
    return data


def _save_telemetry_config_raw(data: Dict[str, Any]) -> None:
    _TELEMETRY_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    _TELEMETRY_CONFIG_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _token_last8(token: str) -> Optional[str]:
    token = (token or "").strip()
    if not token:
        return None
    return token[-8:] if len(token) >= 8 else token


def _telemetry_config_response(raw: Dict[str, Any]) -> TelemetryPluginConfig:
    token = (raw.get("telemetry_token") or "").strip()
    live = _load_live_telemetry_status()
    return TelemetryPluginConfig(
        enabled=bool(raw.get("enabled", False)),
        remote_enabled=bool(raw.get("remote_enabled", False)),
        local_enabled=bool(raw.get("local_enabled", False)),
        dcgm_exporter_enabled=bool(raw.get("dcgm_exporter_enabled", False)),
        grafana_enabled=bool(raw.get("grafana_enabled", False)),
        nvidia_gpu_available=bool((live or {}).get("nvidia_gpu_available", False)),
        gateway_url=(raw.get("gateway_url") or _TELEMETRY_DEFAULTS["gateway_url"]).strip(),
        token_set=bool(token),
        token_last8=_token_last8(token),
        generated_config_path=(raw.get("generated_config_path") or _TELEMETRY_DEFAULTS["generated_config_path"]).strip(),
        local_grafana_running=bool((live or {}).get("local_grafana_running", False)),
        cadvisor_running=bool((live or {}).get("cadvisor_running", False)),
        grafana_url=str((live or {}).get("grafana_url") or "/sys/plugins/telemetry-exporter/grafana/"),
    )


def _load_telemetry_plugin_state() -> Dict[str, Any]:
    if not _TELEMETRY_STATE_PATH.is_file():
        return {}
    try:
        data = json.loads(_TELEMETRY_STATE_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _resolve_local_dms_identity() -> Dict[str, str]:
    """
    Best-effort resolve of local appliance identity labels for telemetry.
    Returns empty values when DMS is unavailable.
    """
    did = ""
    peer_id = ""
    try:
        mgr = DMSManager()
        raw_peer_id = mgr.get_peer_id()
        if isinstance(raw_peer_id, str):
            peer_id = raw_peer_id.strip()
        info = mgr.get_self_peer_info()
        if isinstance(info, dict):
            raw_did = info.get("did") or info.get("DID")
            if isinstance(raw_did, str):
                did = raw_did.strip()
    except Exception:
        pass
    return {"did": did, "peer_id": peer_id}


def _query_prometheus_range(query: str, start_ts: int, end_ts: int, step_seconds: int) -> Dict[int, float]:
    endpoints = [
        "http://127.0.0.1:9009/prometheus/api/v1/query_range",
        "http://127.0.0.1:9009/api/v1/query_range",
    ]
    params = {
        "query": query,
        "start": str(start_ts),
        "end": str(end_ts),
        "step": str(step_seconds),
    }
    query_string = urllib.parse.urlencode(params)
    last_error: Optional[Exception] = None

    for endpoint in endpoints:
        try:
            with urllib.request.urlopen(f"{endpoint}?{query_string}", timeout=8) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            if payload.get("status") != "success":
                continue
            results = ((payload.get("data") or {}).get("result") or [])
            if not results:
                return {}
            # All our queries aggregate to a single series.
            values = results[0].get("values") or []
            parsed: Dict[int, float] = {}
            for point in values:
                if not isinstance(point, list) or len(point) != 2:
                    continue
                ts = int(float(point[0]))
                try:
                    parsed[ts] = float(point[1])
                except (TypeError, ValueError):
                    continue
            return parsed
        except Exception as exc:
            last_error = exc
            continue

    if last_error:
        raise last_error
    return {}

@router.get("/check-updates", response_model=str)
def check_updates():
    return get_appliance_updates()


@router.post("/trigger-update", response_model=CommandResult)
def trigger_update():
    """Triggers the nunet-appliance-updater service."""
    result = trigger_appliance_update()
    return CommandResult(**result)


@router.post("/trigger-plugin-sync", response_model=CommandResult)
def trigger_plugin_sync_endpoint():
    """Triggers the plugin sync systemd service."""
    # Capture latest DID/peer_id before sync so plugin-manager can pass them to hooks.
    identity = _resolve_local_dms_identity()
    if identity.get("did") or identity.get("peer_id"):
        raw = _load_telemetry_config_raw()
        raw["did"] = identity.get("did", "")
        raw["peer_id"] = identity.get("peer_id", "")
        _save_telemetry_config_raw(raw)
    result = trigger_plugin_sync()
    return CommandResult(**result)


@router.post("/plugins/telemetry-exporter/uninstall", response_model=CommandResult)
def uninstall_telemetry_plugin_endpoint():
    """Triggers telemetry plugin uninstall service."""
    result = trigger_telemetry_plugin_uninstall()
    return CommandResult(**result)


@router.get("/plugins/telemetry-exporter/config", response_model=TelemetryPluginConfig)
def get_telemetry_plugin_config():
    return _telemetry_config_response(_load_telemetry_config_raw())


@router.put("/plugins/telemetry-exporter/config", response_model=TelemetryPluginConfig)
def update_telemetry_plugin_config(payload: TelemetryPluginConfigUpdate):
    raw = _load_telemetry_config_raw()
    if payload.enabled is not None:
        raw["enabled"] = payload.enabled
    if payload.remote_enabled is not None:
        raw["remote_enabled"] = payload.remote_enabled
    if payload.local_enabled is not None:
        raw["local_enabled"] = payload.local_enabled
    if payload.dcgm_exporter_enabled is not None:
        raw["dcgm_exporter_enabled"] = payload.dcgm_exporter_enabled
    if payload.grafana_enabled is not None:
        raw["grafana_enabled"] = payload.grafana_enabled
    if payload.gateway_url is not None:
        raw["gateway_url"] = payload.gateway_url.strip() or _TELEMETRY_DEFAULTS["gateway_url"]
    if payload.generated_config_path is not None:
        raw["generated_config_path"] = payload.generated_config_path.strip() or _TELEMETRY_DEFAULTS["generated_config_path"]
    if payload.telemetry_token is not None:
        raw["telemetry_token"] = payload.telemetry_token.strip()
    if bool(raw.get("grafana_enabled", False)):
        # Pro monitoring uses local Mimir as the only datasource.
        raw["local_enabled"] = True
    _save_telemetry_config_raw(raw)
    return _telemetry_config_response(raw)


@router.get("/plugins/telemetry-exporter/status", response_model=TelemetryPluginStatus)
def get_telemetry_plugin_status():
    state = _load_telemetry_plugin_state()
    live_status = _load_live_telemetry_status()
    config = _load_telemetry_config_raw()
    parsed_raw_status = live_status or {}
    token = (config.get("telemetry_token") or "").strip()

    if not parsed_raw_status:
        raw_status = state.get("last_status")
        if isinstance(raw_status, str) and raw_status.strip():
            try:
                parsed_raw_status = json.loads(raw_status)
            except json.JSONDecodeError:
                parsed_raw_status = {"raw": raw_status}
        elif isinstance(raw_status, dict):
            parsed_raw_status = raw_status

    return TelemetryPluginStatus(
        plugin_id=_TELEMETRY_PLUGIN_ID,
        installed_version=state.get("installed_version"),
        updated_at=state.get("updated_at"),
        alloy_installed=(parsed_raw_status or {}).get("alloy_installed"),
        alloy_running=(parsed_raw_status or {}).get("alloy_running"),
        local_mimir_running=(parsed_raw_status or {}).get("local_mimir_running"),
        dcgm_exporter_running=(parsed_raw_status or {}).get("dcgm_exporter_running"),
        local_grafana_running=(parsed_raw_status or {}).get("local_grafana_running"),
        cadvisor_running=(parsed_raw_status or {}).get("cadvisor_running"),
        grafana_enabled=bool(config.get("grafana_enabled", False)),
        grafana_url=str((parsed_raw_status or {}).get("grafana_url") or "/sys/plugins/telemetry-exporter/grafana/"),
        nvidia_gpu_available=(parsed_raw_status or {}).get("nvidia_gpu_available"),
        enabled=bool(config.get("enabled", False)),
        token_set=bool(token),
        raw_status=parsed_raw_status,
    )


async def _proxy_grafana_request(proxy_path: str, request: Request) -> Response:
    base_url = "http://127.0.0.1:3000"
    normalized_path = proxy_path.lstrip("/")
    target = f"{base_url}/{normalized_path}" if normalized_path else f"{base_url}/"
    query_pairs = [(k, v) for k, v in request.query_params.multi_items() if k != "access_token"]
    if query_pairs:
        target = f"{target}?{urllib.parse.urlencode(query_pairs)}"

    body = await request.body() if request.method not in {"GET", "HEAD"} else b""

    forward_headers: Dict[str, str] = {}
    for key, value in request.headers.items():
        key_l = key.lower()
        if key_l in {"host", "authorization", "content-length", "connection", "accept-encoding"}:
            continue
        forward_headers[key] = value
    forward_headers["Host"] = request.url.hostname or "localhost"
    forward_headers["X-Forwarded-Proto"] = request.url.scheme
    forward_headers["X-Forwarded-Host"] = request.headers.get("host", "")

    req = urllib.request.Request(
        target,
        data=(body if body else None),
        headers=forward_headers,
        method=request.method,
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as upstream:
            payload = upstream.read()
            status_code = upstream.getcode()
            upstream_headers = dict(upstream.headers.items())
    except urllib.error.HTTPError as exc:
        payload = exc.read()
        status_code = exc.code
        upstream_headers = dict(exc.headers.items())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Grafana proxy unavailable: {exc}") from exc

    response_headers: Dict[str, str] = {}
    for key, value in upstream_headers.items():
        key_l = key.lower()
        if key_l in {"content-length", "transfer-encoding", "connection", "content-encoding"}:
            continue
        response_headers[key] = value
    response = Response(content=payload, status_code=status_code, headers=response_headers)
    access_token = request.query_params.get("access_token")
    if access_token:
        # Persist auth for subsequent Grafana static/app requests under this subpath.
        response.set_cookie(
            key="nunet_admin_token",
            value=access_token,
            httponly=True,
            secure=(request.url.scheme == "https"),
            samesite="lax",
            path="/sys/plugins/telemetry-exporter/grafana",
        )
    return response


@router.api_route("/plugins/telemetry-exporter/grafana", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"])
async def proxy_grafana_root(request: Request):
    return await _proxy_grafana_request("", request)


@router.api_route("/plugins/telemetry-exporter/grafana/{proxy_path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"])
async def proxy_grafana_subpath(proxy_path: str, request: Request):
    return await _proxy_grafana_request(proxy_path, request)


@router.get("/plugins/telemetry-exporter/local-metrics", response_model=TelemetryLocalMetricsResponse)
def get_telemetry_local_metrics(
    range_minutes: int = Query(60, ge=15, le=30 * 24 * 60),
    step_seconds: int = Query(30, ge=10, le=3600),
):
    live = _load_live_telemetry_status()
    config = _load_telemetry_config_raw()
    if not bool(config.get("local_enabled", False)) and not bool(config.get("grafana_enabled", False)):
        return TelemetryLocalMetricsResponse(
            available=False,
            reason="Local collection is disabled.",
            range_minutes=range_minutes,
            step_seconds=step_seconds,
            points=[],
        )
    if not bool((live or {}).get("local_mimir_running", False)):
        return TelemetryLocalMetricsResponse(
            available=False,
            reason="Local Mimir is not running.",
            range_minutes=range_minutes,
            step_seconds=step_seconds,
            points=[],
        )

    end_ts = int(time.time())
    range_seconds = range_minutes * 60
    start_ts = end_ts - range_seconds
    # Keep payloads bounded for long ranges and multiple series.
    max_points = 900
    effective_step_seconds = max(step_seconds, int(math.ceil(range_seconds / max_points)))
    metric_queries = {
        "cpu_percent": '100 - (avg(rate(node_cpu_seconds_total{mode="idle"}[2m])) * 100)',
        "memory_percent": "(1 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)) * 100",
        "disk_utilization_percent": '100 * (1 - (sum(node_filesystem_avail_bytes{fstype!~"tmpfs|overlay|squashfs|ramfs"}) / sum(node_filesystem_size_bytes{fstype!~"tmpfs|overlay|squashfs|ramfs"})))',
        "disk_read_bytes_per_sec": "sum(rate(node_disk_read_bytes_total[2m]))",
        "disk_write_bytes_per_sec": "sum(rate(node_disk_written_bytes_total[2m]))",
        "network_rx_bytes_per_sec": 'sum(rate(node_network_receive_bytes_total{device!~"lo|docker.*|veth.*|br-.*"}[2m]))',
        "network_tx_bytes_per_sec": 'sum(rate(node_network_transmit_bytes_total{device!~"lo|docker.*|veth.*|br-.*"}[2m]))',
        # DCGM exporter metrics (present only when NVIDIA GPU + DCGM exporter are enabled).
        "gpu_utilization_percent": "avg(DCGM_FI_DEV_GPU_UTIL)",
        "gpu_temp_celsius": "avg(DCGM_FI_DEV_GPU_TEMP)",
        "gpu_vram_used_mib": "sum(DCGM_FI_DEV_FB_USED)",
    }

    series: Dict[str, Dict[int, float]] = {}
    try:
        for key, prom_query in metric_queries.items():
            series[key] = _query_prometheus_range(prom_query, start_ts, end_ts, effective_step_seconds)
    except Exception as e:
        return TelemetryLocalMetricsResponse(
            available=False,
            reason=f"Failed to query local metrics: {e}",
            range_minutes=range_minutes,
            step_seconds=effective_step_seconds,
            points=[],
        )

    points: List[TelemetryLocalMetricPoint] = []
    for ts in range(start_ts, end_ts + 1, effective_step_seconds):
        points.append(
            TelemetryLocalMetricPoint(
                ts=ts,
                cpu_percent=series.get("cpu_percent", {}).get(ts),
                memory_percent=series.get("memory_percent", {}).get(ts),
                disk_utilization_percent=series.get("disk_utilization_percent", {}).get(ts),
                disk_read_bytes_per_sec=series.get("disk_read_bytes_per_sec", {}).get(ts),
                disk_write_bytes_per_sec=series.get("disk_write_bytes_per_sec", {}).get(ts),
                network_rx_bytes_per_sec=series.get("network_rx_bytes_per_sec", {}).get(ts),
                network_tx_bytes_per_sec=series.get("network_tx_bytes_per_sec", {}).get(ts),
                gpu_utilization_percent=series.get("gpu_utilization_percent", {}).get(ts),
                gpu_temp_celsius=series.get("gpu_temp_celsius", {}).get(ts),
                gpu_vram_used_mib=series.get("gpu_vram_used_mib", {}).get(ts),
            )
        )

    return TelemetryLocalMetricsResponse(
        available=True,
        reason=None,
        range_minutes=range_minutes,
        step_seconds=effective_step_seconds,
        points=points,
    )


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


@router.get("/environment", response_model=EnvironmentStatus)
def environment_status():
    return EnvironmentStatus(**get_environment_status())

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
