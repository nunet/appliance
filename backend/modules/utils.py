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

from .path_constants import APPLIANCE_PUBLIC_IP_CACHE, GITLAB_PACKAGES_URL

try:
    from backend import __version__
except ImportError:
    # Fallback for PEX builds where backend package structure may differ
    try:
        from _version import __version__
    except ImportError:
        __version__ = "0.0.0"


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


def _resolve_appliance_version() -> str:
    """
    Best-effort loader for the backend package version that tolerates various
    import contexts (e.g., running from backend/, repo root, or an installed wheel).
    """
    try:
        from backend import __version__ as version  # type: ignore

        if isinstance(version, str):
            return version
    except Exception:
        pass

    init_path = Path(__file__).resolve().parents[1] / "__init__.py"
    if init_path.exists():
        try:
            namespace: Dict[str, Any] = {}
            exec(init_path.read_text(), namespace)
            version = namespace.get("__version__")
            if isinstance(version, str):
                return version
        except Exception:
            pass

    return "Unknown"


APPLIANCE_VERSION = _resolve_appliance_version()


def get_appliance_version() -> str:
    """Read the appliance version from the package metadata."""
    return APPLIANCE_VERSION


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


def trigger_appliance_update() -> Dict[str, Any]:
    """Triggers the systemd service to update the appliance asynchronously."""
    try:
        # Use Popen to start the process and not wait for it to complete.
        # This avoids the API process being killed when the updater restarts it.
        subprocess.Popen(
            ["sudo", "-n", "systemctl", "start", "nunet-appliance-updater.service"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return {
            "status": "success",
            "message": "Update service triggered successfully. The update is running in the background.",
            "stdout": "",
            "stderr": "",
            "returncode": 0,
        }
    except Exception as e:
        # This will catch errors like "sudo not found" or immediate permission errors.
        return {
            "status": "error",
            "message": f"Unexpected error triggering update: {e}",
            "stdout": "",
            "stderr": "",
            "returncode": None,
        }


def fetch_latest_appliance() -> str:
    """Fetch the latest appliance version from the Gitlab package registry."""
    try:
        import urllib.request
        import json

        with urllib.request.urlopen(GITLAB_PACKAGES_URL, timeout=5) as response:
            packages = json.loads(response.read().decode("utf-8"))
            if packages:
                return packages[0]["version"].strip()
            return ""
    except Exception:
        return ""


def get_updates() -> str:
    """Compare the current appliance version with the latest available."""
    latest_version = fetch_latest_appliance()
    current_version = get_appliance_version()

    if not latest_version:
        return json.dumps({"available": False, "current": current_version, "latest": latest_version})

    if latest_version == current_version:
        return json.dumps({"available": False, "current": current_version, "latest": latest_version})

    try:
        # Compare versions like "1.2.3" > "1.2.2"
        latest_parts = [int(p) for p in latest_version.split(".")]
        current_parts = [int(p) for p in current_version.split(".")]
        available = latest_parts > current_parts
    except (ValueError, IndexError):
        # Fallback for non-numeric versions (e.g. "Unknown", or "1.2.3-beta")
        # We already checked for equality, so if they differ, we'll suggest an update.
        available = True

    return json.dumps({
        "available": available,
        "current": current_version,
        "latest": latest_version,
    })
