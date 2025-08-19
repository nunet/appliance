# nunet_api/app/routers/sysinfo.py
from fastapi import APIRouter, Depends
from ..schemas import SshStatus
from ..adapters import parse_ssh_status
from modules.utils import get_local_ip, get_public_ip, get_appliance_version, get_ssh_status

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
