from typing import Dict

from fastapi import APIRouter, Query

from modules.appliance_manager import ApplianceManager
from ..schemas import ApplianceUptime

router = APIRouter()


@router.get("/uptime", response_model=ApplianceUptime)
def get_system_uptime():
    """
    Retrieve the system uptime.
    """
    manager = ApplianceManager()
    uptime_str = manager.get_uptime()
    return ApplianceUptime(uptime=uptime_str)


@router.get("/logs", response_model=Dict[str, str])
def get_systemd_logs(lines: int = Query(50, description="Number of log lines to retrieve per service.", gt=0, le=1000)):
    """
    Retrieve the latest logs for predefined systemd services.
    """
    manager = ApplianceManager()
    return manager.get_systemd_logs(lines=lines)
