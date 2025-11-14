"""
Minimal utility helpers used by the FastAPI backend.

Only the functions referenced by API routers are preserved.  The terminal menu
helpers, ANSI colour wrappers, and configuration management logic have been
removed along with the legacy UI.
"""

import json
import socket
import subprocess
import time
from pathlib import Path
from typing import Any, Dict

try:
    from backend import __version__
except ImportError:
    # Fallback for PEX builds where backend package structure may differ
    try:
        from _version import __version__
    except ImportError:
        __version__ = "0.0.0"

from .path_constants import APPLIANCE_PUBLIC_IP_CACHE


def get_local_ip() -> str:
    """Return the machine's perceived local IPv4 address."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("10.255.255.255", 1))
            return sock.getsockname()[0]
    except Exception:
        return "127.0.0.1"


def get_public_ip(cache_ttl: int = 3600) -> str:
    """
    Fetch the public IP address with a simple TTL cache to avoid hammering the service.
    """
    now = time.time()
    cache: Dict[str, Any] = {}

    if APPLIANCE_PUBLIC_IP_CACHE.exists():
        try:
            cache = json.loads(APPLIANCE_PUBLIC_IP_CACHE.read_text())
        except Exception:
            cache = {}

    last_checked = float(cache.get("last_checked", 0))
    cached_ip = cache.get("ip")
    if cached_ip and now - last_checked < cache_ttl:
        return cached_ip

    try:
        import urllib.request

        with urllib.request.urlopen("https://api.ipify.org", timeout=5) as response:
            ip = response.read().decode("utf-8")
    except Exception:
        return cached_ip or "Unavailable"

    APPLIANCE_PUBLIC_IP_CACHE.parent.mkdir(parents=True, exist_ok=True)
    APPLIANCE_PUBLIC_IP_CACHE.write_text(json.dumps({"ip": ip, "last_checked": now}))
    return ip


def get_appliance_version() -> str:
    """Read the appliance version from the package metadata."""
    return __version__


def get_ssh_status() -> str:
    """
    Return a lightweight summary of the SSH service state and the number of authorised keys.
    """
    try:
        status = subprocess.run(
            ["systemctl", "is-active", "ssh"],
            capture_output=True,
            text=True,
            check=False,
        )
        running = (status.stdout or "").strip() == "active"
    except Exception:
        running = False

    auth_keys = Path.home() / ".ssh" / "authorized_keys"
    try:
        if auth_keys.exists():
            count = sum(
                1 for line in auth_keys.read_text().splitlines() if line.strip() and not line.strip().startswith("#")
            )
        else:
            count = 0
    except Exception:
        count = 0

    service = "Running" if running else "Stopped"
    return f"SSH: {service} | Authorized Keys: {count}"
