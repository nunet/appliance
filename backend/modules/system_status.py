# modules/system_status.py
import threading
from copy import deepcopy
from time import monotonic

from modules.utils import (
    get_current_branch,
    get_local_ip,
    get_public_ip,
    get_appliance_version,
    format_status,
    get_ssh_status,
)
from modules.docker_manager import DockerManager
from modules.appliance_manager import ApplianceManager
from modules.caddy_proxy_manager import CaddyProxyManager
from modules.dms_utils import (
    get_cached_dms_status_info,
    get_cached_dms_resource_info,
)


_SYSTEM_STATUS_CACHE_TTL = 30.0
_SYSTEM_STATUS_CACHE_LOCK = threading.Lock()
_SYSTEM_STATUS_CACHE = {"data": None, "timestamp": 0.0}


def _compute_system_status(force_refresh: bool = False) -> dict:
    """Collect the latest system status snapshot."""
    docker_mgr = DockerManager()
    app_mgr = ApplianceManager()

    status = {
        "local_ip": get_local_ip(),
        "public_ip": get_public_ip(),
        "appliance_version": get_appliance_version(),
        "current_branch": get_current_branch(),
        "menu_version": app_mgr.get_current_version(),
        "docker_status": format_status(docker_mgr.check_docker_status().get("status", "Unknown")),
        "ssh_status": get_ssh_status(),
        "caddy_status": CaddyProxyManager.get_caddy_proxy_status(),
    }

    unattended = app_mgr.get_unattended_upgrades_status()
    status.update(
        {
            "unattended_enabled": unattended.get("enabled"),
            "unattended_last_run": unattended.get("last_run"),
        }
    )

    dms_status = get_cached_dms_status_info(force_refresh=force_refresh)
    if dms_status:
        status.update(dms_status)
        status["dms_running"] = format_status(dms_status.get("dms_running", "Not Running"))

    dms_resources = get_cached_dms_resource_info(force_refresh=force_refresh)
    if dms_resources:
        status.update(dms_resources)

    return status


def get_system_status(force_refresh: bool = False) -> dict:
    """Return a cached system status snapshot, refreshing at most every 30 seconds."""
    if not force_refresh:
        with _SYSTEM_STATUS_CACHE_LOCK:
            cached = _SYSTEM_STATUS_CACHE["data"]
            ts = _SYSTEM_STATUS_CACHE["timestamp"]
            if cached is not None and monotonic() - ts < _SYSTEM_STATUS_CACHE_TTL:
                return deepcopy(cached)

    snapshot = _compute_system_status(force_refresh=force_refresh)

    with _SYSTEM_STATUS_CACHE_LOCK:
        _SYSTEM_STATUS_CACHE["data"] = snapshot
        _SYSTEM_STATUS_CACHE["timestamp"] = monotonic()

    return deepcopy(snapshot)

