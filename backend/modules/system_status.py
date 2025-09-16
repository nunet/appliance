# modules/system_status.py
from modules.utils import (
    get_current_branch, get_local_ip, get_public_ip, get_appliance_version,
    format_status, get_ssh_status
)
from modules.dms_manager import DMSManager
from modules.docker_manager import DockerManager
from modules.appliance_manager import ApplianceManager
from modules.caddy_proxy_manager import CaddyProxyManager

def get_system_status() -> dict:
    """Return a dict with all fields the TUI header shows."""
    docker_mgr   = DockerManager()
    dms_mgr      = DMSManager()
    app_mgr      = ApplianceManager()
    caddy_mgr    = CaddyProxyManager()

    status = {
        # “static” information
        "local_ip"          : get_local_ip(),
        "public_ip"         : get_public_ip(),
        "appliance_version" : get_appliance_version(),
        "current_branch"    : get_current_branch(),
        "menu_version"      : app_mgr.get_current_version(),
        # services
        "docker_status"     : format_status(docker_mgr.check_docker_status()['status']),
        "ssh_status"        : get_ssh_status(),
        "caddy_status"      : caddy_mgr.get_caddy_proxy_status(),
    }

    # unattended‑upgrade info (already cached in ApplianceManager)
    unattended = app_mgr.get_unattended_upgrades_status()
    status.update({
        "unattended_enabled" : unattended['enabled'],
        "unattended_last_run": unattended['last_run'],
    })

    # DMS detailed status
    status.update(dms_mgr.update_dms_status())

    return status
