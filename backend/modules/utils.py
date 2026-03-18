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
from urllib.error import URLError, HTTPError
from urllib.request import Request, urlopen
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from .environment_profile import (
    RuntimeProfile,
    UpdateChannel,
    build_package_url,
    detect_deb_arch,
    get_runtime_profile,
    iter_package_candidates,
)
from .path_constants import (
    APPLIANCE_PUBLIC_IP_CACHE,
    APPLIANCE_UPDATE_CACHE,
    GITLAB_DMS_PACKAGES_URL,
    GITLAB_PACKAGES_URL,
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


def _parse_version_parts(value: str) -> Optional[list[int]]:
    match = re.match(r"\s*v?(\d+)(?:\.(\d+))?(?:\.(\d+))?", value or "")
    if not match:
        return None
    return [
        int(match.group(1) or 0),
        int(match.group(2) or 0),
        int(match.group(3) or 0),
    ]


def _normalize_version(value: str) -> str:
    return (value or "").strip().lower().lstrip("v")


def _dpkg_lt_version(current: str, latest: str) -> Optional[bool]:
    """
    Return whether ``current < latest`` using dpkg version semantics.

    Returns:
    - True/False when dpkg comparison is conclusive.
    - None when dpkg is unavailable or the input is invalid for dpkg parsing.
    """
    try:
        cp = subprocess.run(
            ["dpkg", "--compare-versions", current, "lt", latest],
            capture_output=True,
            text=True,
            check=False,
        )
    except Exception:
        return None

    if cp.returncode == 0:
        return True
    if cp.returncode == 1:
        return False
    return None


def _is_remote_version_newer(current: str, latest: str) -> bool:
    """
    Determine whether ``latest`` should be considered newer than ``current``.

    Priority:
    1) dpkg version comparison (handles Debian revisions like 1.2.3-4).
    2) Numeric semver prefix comparison.
    3) Normalized full-string comparison fallback.
    """
    current_norm = _normalize_version(current)
    latest_norm = _normalize_version(latest)
    if not current_norm or not latest_norm:
        return False
    if current_norm == latest_norm:
        return False

    dpkg_lt = _dpkg_lt_version(current_norm, latest_norm)
    if dpkg_lt is not None:
        return dpkg_lt

    latest_parts = _parse_version_parts(latest_norm)
    current_parts = _parse_version_parts(current_norm)
    if latest_parts and current_parts and latest_parts != current_parts:
        return latest_parts > current_parts

    return latest_norm > current_norm


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
    Read the Debian package version from a .deb permalink.

    Uses response metadata to avoid downloading the package unless it changed.
    """
    try:
        req = Request(url, method="HEAD")
        with urlopen(req, timeout=8) as response:
            etag = response.headers.get("ETag") or ""
            last_modified = response.headers.get("Last-Modified") or ""
            content_length = response.headers.get("Content-Length") or ""
    except URLError:
        return ""
    except Exception:
        return ""

    cache = _read_update_cache()
    entry = cache.get(cache_key, {}) if isinstance(cache, dict) else {}
    cached_version = str(entry.get("version") or "")
    cache_etag = str(entry.get("etag") or "")
    cache_last_modified = str(entry.get("last_modified") or "")
    cache_length = str(entry.get("content_length") or "")

    if cached_version and etag and etag == cache_etag:
        return cached_version
    if cached_version and not etag and last_modified and last_modified == cache_last_modified:
        return cached_version
    if cached_version and not etag and not last_modified and content_length and content_length == cache_length:
        return cached_version

    try:
        with tempfile.NamedTemporaryFile(suffix=".deb", delete=True) as tmp_file:
            with urlopen(url, timeout=20) as response:
                tmp_file.write(response.read())
                tmp_file.flush()
            cp = subprocess.run(
                ["dpkg-deb", "-f", tmp_file.name, "Version"],
                capture_output=True,
                text=True,
                check=False,
            )
        if cp.returncode != 0:
            return ""
        version = (cp.stdout or "").strip()
        if ":" in version:
            version = version.split(":", 1)[1].strip()
    except Exception:
        return ""

    cache[cache_key] = {
        "version": version,
        "etag": etag,
        "last_modified": last_modified,
        "content_length": content_length,
        "checked_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
    }
    _write_update_cache(cache)
    return version


def _url_exists(url: str, timeout: int = 5) -> bool:
    try:
        req = Request(url, method="HEAD")
        with urlopen(req, timeout=timeout) as response:
            status = getattr(response, "status", 200)
            return 200 <= int(status) < 400
    except HTTPError:
        return False
    except URLError:
        return False
    except Exception:
        return False


def _package_policy_for_kind(profile: RuntimeProfile, kind: str):
    return profile.appliance_updates if kind == "appliance" else profile.dms_updates


def _resolve_latest_from_channels(
    kind: str,
    profile: RuntimeProfile,
) -> Tuple[str, UpdateChannel, bool]:
    policy = _package_policy_for_kind(profile, kind)
    arch = detect_deb_arch()
    if not arch:
        return "", policy.preferred_channel, False

    candidates = iter_package_candidates(kind, arch, policy)
    for idx, (channel, url) in enumerate(candidates):
        version = _deb_version_from_url(url, f"{kind}:{arch}:{channel}")
        if version:
            return version, channel, idx > 0
    return "", policy.preferred_channel, False


def _fetch_registry_version(kind: str) -> str:
    registry_url = GITLAB_PACKAGES_URL if kind == "appliance" else GITLAB_DMS_PACKAGES_URL
    try:
        with urlopen(registry_url, timeout=5) as response:
            packages = json.loads(response.read().decode("utf-8"))
            if packages:
                return packages[0]["version"].strip()
            return ""
    except Exception:
        return ""


def _build_update_details(kind: str) -> Dict[str, Any]:
    profile = get_runtime_profile()
    latest, resolved_channel, fell_back = _resolve_latest_from_channels(kind, profile)
    if not latest:
        latest = _fetch_registry_version(kind)
    channel = _package_policy_for_kind(profile, kind).preferred_channel
    return {
        "environment": profile.environment,
        "channel": channel,
        "resolved_channel": resolved_channel,
        "fell_back": fell_back,
        "latest": latest,
    }


def _resolve_fallback_state(kind: str, profile: RuntimeProfile) -> Tuple[UpdateChannel, bool]:
    policy = _package_policy_for_kind(profile, kind)
    if not policy.fallback_channel:
        return policy.preferred_channel, False
    arch = detect_deb_arch()
    if not arch:
        return policy.preferred_channel, False
    preferred_url = build_package_url(kind, arch, policy.preferred_channel)
    if _url_exists(preferred_url):
        return policy.preferred_channel, False
    fallback_url = build_package_url(kind, arch, policy.fallback_channel)
    if _url_exists(fallback_url):
        return policy.fallback_channel, True
    return policy.preferred_channel, False


def get_environment_status() -> Dict[str, Any]:
    profile = get_runtime_profile()
    appliance_resolved_channel, appliance_fell_back = _resolve_fallback_state("appliance", profile)
    dms_resolved_channel, dms_fell_back = _resolve_fallback_state("dms", profile)
    return {
        "environment": profile.environment,
        "updates": {
            "appliance": {
                "channel": profile.appliance_updates.preferred_channel,
                "resolved_channel": appliance_resolved_channel,
                "fell_back": appliance_fell_back,
            },
            "dms": {
                "channel": profile.dms_updates.preferred_channel,
                "resolved_channel": dms_resolved_channel,
                "fell_back": dms_fell_back,
            },
        },
        "ethereum": {
            "chain_id": profile.ethereum.chain_id,
            "token_address": profile.ethereum.token_address,
            "token_symbol": profile.ethereum.token_symbol,
            "token_decimals": profile.ethereum.token_decimals,
            "explorer_base_url": profile.ethereum.explorer_base_url,
            "network_name": profile.ethereum.network_name,
        },
    }


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
    """Fetch the latest appliance version for the active environment channel policy."""
    return str(_build_update_details("appliance").get("latest", ""))


def fetch_latest_dms_version() -> str:
    """Fetch the latest DMS version for the active environment channel policy."""
    return str(_build_update_details("dms").get("latest", ""))


def get_updates(details: dict, latest_version: str, current_version: str) -> str:
    """Compare the current version with the latest available."""
    if not latest_version or not current_version or current_version in ("Not Installed", "Unknown"):
        return json.dumps({
            "available": False,
            "current": current_version,
            "latest": latest_version,
            "environment": details["environment"],
            "channel": details["channel"],
            "resolved_channel": details["resolved_channel"],
        })

    if _normalize_version(latest_version) == _normalize_version(current_version):
        return json.dumps({
            "available": False,
            "current": current_version,
            "latest": latest_version,
            "environment": details["environment"],
            "channel": details["channel"],
            "resolved_channel": details["resolved_channel"],
        })
    available = _is_remote_version_newer(current_version, latest_version)

    return json.dumps({
        "available": available,
        "current": current_version,
        "latest": latest_version,
        "environment": details["environment"],
        "channel": details["channel"],
        "resolved_channel": details["resolved_channel"],
    })


def get_appliance_updates() -> str:
    """Compare the current appliance version with the latest available."""
    details = _build_update_details("appliance")
    latest_version = str(details.get("latest") or "")
    current_version = get_appliance_version()

    return get_updates(details, latest_version, current_version)


def get_dms_updates() -> str:
    """Compare the current DMS version with the latest available."""
    from modules.dms_manager import DMSManager

    details = _build_update_details("dms")
    latest_version = str(details.get("latest") or "")
    mgr = DMSManager()
    current_version = mgr.get_dms_version()

    return get_updates(details, latest_version, current_version)

