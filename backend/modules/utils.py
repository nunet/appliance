"""
Minimal utility helpers used by the FastAPI backend.

Only the functions referenced by API routers are preserved.  The terminal menu
helpers, ANSI colour wrappers, and configuration management logic have been
removed along with the legacy UI.
"""

import json
import re
import socket
import subprocess
import tempfile
import time
from datetime import datetime
from urllib.error import URLError
from urllib.request import Request, urlopen
from pathlib import Path
from typing import Any, Dict, Optional

from .path_constants import (
    APPLIANCE_PUBLIC_IP_CACHE,
    APPLIANCE_UPDATE_CACHE,
    GITLAB_PACKAGES_URL,
    GITLAB_DMS_PACKAGES_URL,
)

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
    Best-effort loader for the appliance version that tolerates various
    import contexts (installed package, repo root, or PEX builds).
    """
    # Prefer the installed Debian package version when available.
    try:
        result = subprocess.run(
            ["dpkg-query", "-W", "-f=${Version}", "nunet-appliance-web"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            raw_version = (result.stdout or "").strip()
            if raw_version:
                # Strip Debian epoch (e.g., "1:0.6.4") for semver comparisons.
                if ":" in raw_version:
                    raw_version = raw_version.split(":", 1)[1].strip()
                return raw_version
    except Exception:
        pass

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


def get_appliance_version() -> str:
    """Read the appliance version from the package metadata."""
    return _resolve_appliance_version()


def _parse_version_parts(value: str) -> Optional[list[int]]:
    match = re.match(r"\s*v?(\d+)(?:\.(\d+))?(?:\.(\d+))?", value)
    if not match:
        return None
    return [
        int(match.group(1) or 0),
        int(match.group(2) or 0),
        int(match.group(3) or 0),
    ]


def _normalize_version(value: str) -> str:
    return value.strip().lower().lstrip("v")


def _read_update_cache() -> Dict[str, Any]:
    if not APPLIANCE_UPDATE_CACHE.exists():
        return {}
    try:
        return json.loads(APPLIANCE_UPDATE_CACHE.read_text())
    except Exception:
        return {}


def _write_update_cache(cache: Dict[str, Any]) -> None:
    APPLIANCE_UPDATE_CACHE.parent.mkdir(parents=True, exist_ok=True)
    APPLIANCE_UPDATE_CACHE.write_text(json.dumps(cache))


def _deb_version_from_url(url: str, cache_key: str) -> str:
    """
    Fetch a .deb version from a URL, caching by ETag/Last-Modified to avoid
    repeated large downloads.
    """
    try:
        req = Request(url, method="HEAD")
        with urlopen(req, timeout=5) as response:
            etag = response.headers.get("ETag") or ""
            last_modified = response.headers.get("Last-Modified") or ""
            content_length = response.headers.get("Content-Length") or ""
    except URLError:
        return ""

    cache = _read_update_cache()
    cache_entry = cache.get(cache_key, {})
    cache_etag = cache_entry.get("etag") or ""
    cache_last_modified = cache_entry.get("last_modified") or ""
    cache_length = cache_entry.get("content_length") or ""
    cached_version = cache_entry.get("version") or ""

    if cached_version and etag and etag == cache_etag:
        return cached_version
    if cached_version and not etag and last_modified and last_modified == cache_last_modified:
        return cached_version
    if cached_version and not etag and not last_modified and content_length == cache_length:
        return cached_version

    try:
        with tempfile.NamedTemporaryFile(suffix=".deb", delete=True) as tmp_file:
            with urlopen(url, timeout=15) as response:
                tmp_file.write(response.read())
                tmp_file.flush()
            result = subprocess.run(
                ["dpkg-deb", "-f", tmp_file.name, "Version"],
                capture_output=True,
                text=True,
                check=False,
            )
        if result.returncode != 0:
            return ""
        raw_version = (result.stdout or "").strip()
        if ":" in raw_version:
            raw_version = raw_version.split(":", 1)[1].strip()
    except Exception:
        return ""

    cache[cache_key] = {
        "version": raw_version,
        "etag": etag,
        "last_modified": last_modified,
        "content_length": content_length,
        "checked_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
    }
    _write_update_cache(cache)
    return raw_version


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


def trigger_dms_update() -> Dict[str, Any]:
    """Triggers the systemd service to update DMS asynchronously."""
    try:
        # Use Popen to start the process and not wait for it to complete.
        # This avoids the API process being killed when the updater restarts it.
        subprocess.Popen(
            ["sudo", "-n", "systemctl", "start", "nunet-dms-updater.service"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return {
            "status": "success",
            "message": "DMS update service triggered successfully. The update is running in the background.",
            "stdout": "",
            "stderr": "",
            "returncode": 0,
        }
    except Exception as e:
        # This will catch errors like "sudo not found" or immediate permission errors.
        return {
            "status": "error",
            "message": f"Unexpected error triggering DMS update: {e}",
            "stdout": "",
            "stderr": "",
            "returncode": None,
        }


def fetch_latest_appliance() -> str:
    """Fetch the latest appliance version from the Gitlab package registry."""
    try:
        arch = subprocess.run(
            ["dpkg", "--print-architecture"],
            capture_output=True,
            text=True,
            check=False,
        ).stdout.strip()
        if arch:
            deb_url = f"https://d.nunet.io/nunet-appliance-web-{arch}-latest.deb"
            deb_version = _deb_version_from_url(deb_url, f"appliance:{arch}")
            if deb_version:
                return deb_version
    except Exception:
        pass

    try:
        with urlopen(GITLAB_PACKAGES_URL, timeout=5) as response:
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

    latest_parts = _parse_version_parts(latest_version)
    current_parts = _parse_version_parts(current_version)
    if latest_parts and current_parts:
        available = latest_parts > current_parts
    else:
        # Fallback for non-numeric versions (e.g. "Unknown", or "1.2.3-beta")
        available = _normalize_version(latest_version) != _normalize_version(current_version)

    return json.dumps({
        "available": available,
        "current": current_version,
        "latest": latest_version,
    })


def fetch_latest_dms_version() -> str:
    """Fetch the latest DMS version from the Gitlab package registry."""
    try:
        arch = subprocess.run(
            ["dpkg", "--print-architecture"],
            capture_output=True,
            text=True,
            check=False,
        ).stdout.strip()
        if arch:
            deb_url = f"https://d.nunet.io/nunet-dms-{arch}-latest.deb"
            deb_version = _deb_version_from_url(deb_url, f"dms:{arch}")
            if deb_version:
                return deb_version
    except Exception:
        pass

    try:
        with urlopen(GITLAB_DMS_PACKAGES_URL, timeout=5) as response:
            packages = json.loads(response.read().decode("utf-8"))
            if packages:
                return packages[0]["version"].strip()
            return ""
    except Exception:
        return ""


def get_dms_updates() -> str:
    """Compare the current DMS version with the latest available."""
    from modules.dms_manager import DMSManager

    latest_version = fetch_latest_dms_version()
    mgr = DMSManager()
    current_version = mgr.get_dms_version()

    if not latest_version or not current_version or current_version in ("Not Installed", "Unknown"):
        return json.dumps({
            "available": False,
            "current": current_version or "Unknown",
            "latest": latest_version or "Unknown"
        })

    if latest_version == current_version:
        return json.dumps({
            "available": False,
            "current": current_version,
            "latest": latest_version
        })

    latest_parts = _parse_version_parts(latest_version)
    current_parts = _parse_version_parts(current_version)
    if latest_parts and current_parts:
        available = latest_parts > current_parts
    else:
        # Fallback for non-numeric versions (e.g. "Unknown", or "1.2.3-beta")
        available = _normalize_version(latest_version) != _normalize_version(current_version)

    return json.dumps({
        "available": available,
        "current": current_version,
        "latest": latest_version
    })
