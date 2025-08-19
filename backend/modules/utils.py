"""
Utility functions and classes for the NuNet menu system
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import time
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional

# -------------------------
# ANSI colors (public API preserved)
# -------------------------

class Colors:
    """ANSI color codes for terminal output"""
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN = "\033[96m"
    NC = "\033[0m"  # No Color


# -------------------------
# Paths & constants
# -------------------------

# Keep original behavior: some features use ~/.config, others use fixed /home/ubuntu paths.
CONFIG_DIR_DEFAULT = Path.home() / ".config" / "nunet"
CONFIG_FILE_NAME = "menu_config.json"

# Fixed-path files preserved as in original:
APPLIANCE_PUBLIC_IP_CACHE = Path("/home/ubuntu/nunet/appliance/public_ip_cache.json")
APPLIANCE_VERSION_FILE = Path("/home/ubuntu/nunet/appliance/appliance_version.txt")

BRANCH_FILE_NAME = "menu_branch.txt"  # stored under get_appliance_dir()


# -------------------------
# Config Manager (API preserved)
# -------------------------

class ConfigManager:
    """Manages configuration file operations"""

    def __init__(self, config_dir: Optional[Path] = None) -> None:
        self.config_dir = config_dir or CONFIG_DIR_DEFAULT
        self.config_file = self.config_dir / CONFIG_FILE_NAME
        self._ensure_config_dir()

    def _ensure_config_dir(self) -> None:
        """Ensure the configuration directory exists"""
        self.config_dir.mkdir(parents=True, exist_ok=True)

    def load_config(self) -> Dict[str, Any]:
        """Load configuration from file"""
        if not self.config_file.exists():
            return {}
        try:
            return json.loads(self.config_file.read_text())
        except json.JSONDecodeError:
            return {}

    def save_config(self, config: Dict[str, Any]) -> None:
        """Save configuration to file"""
        # Write atomically to reduce risk of partial writes
        tmp = self.config_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(config, indent=4))
        tmp.replace(self.config_file)


# -------------------------
# Console helpers
# -------------------------

def clear_screen() -> None:
    """Clear the terminal screen"""
    os.system("clear" if os.name == "posix" else "cls")


def pause() -> None:
    """Pause execution until user presses Enter"""
    input("\nPress Enter to continue...")


def format_status(status: str, color: bool = True) -> str:
    """Format a status string with color (set mapping preserved)"""
    if not color:
        return status

    s = status.lower()
    success = {"running", "installed", "active", "success"}
    error = {"not running", "not installed", "inactive", "error"}
    warning = {"warning", "pending"}

    if s in success:
        return f"{Colors.GREEN}{status}{Colors.NC}"
    if s in error:
        return f"{Colors.RED}{status}{Colors.NC}"
    if s in warning:
        return f"{Colors.YELLOW}{status}{Colors.NC}"
    return status


def print_header(title: str) -> None:
    """Print a formatted header"""
    clear_screen()
    print(f"\n{Colors.CYAN}🌟 {title}{Colors.NC}")
    print("=" * 50)


def print_menu_option(number: str, text: str, emoji: str = "") -> None:
    """Print a formatted menu option"""
    print(f"{number}) {emoji} {text}")


# -------------------------
# Filesystem helpers (API preserved)
# -------------------------

def get_appliance_dir() -> Path:
    """Get the NuNet appliance directory"""
    return Path.home() / "nunet" / "appliance"


def _branch_file() -> Path:
    return get_appliance_dir() / BRANCH_FILE_NAME


def get_current_branch() -> str:
    """Get current branch from menu_branch.txt"""
    bf = _branch_file()
    try:
        return bf.read_text().strip()
    except FileNotFoundError:
        bf.parent.mkdir(parents=True, exist_ok=True)
        bf.write_text("main")
        return "main"


def set_current_branch(branch: str) -> None:
    """Set the current branch in menu_branch.txt"""
    bf = _branch_file()
    bf.parent.mkdir(parents=True, exist_ok=True)
    bf.write_text(branch)


# -------------------------
# Networking helpers (API preserved)
# -------------------------

def get_local_ip() -> str:
    """Return the machine's local IPv4 address (best-effort)."""
    # Using a non-routable address ensures we don't actually connect
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"


def get_public_ip() -> str:
    """Get the public (internet) IP address of this machine, rate-limited to once per hour."""
    cache_file = APPLIANCE_PUBLIC_IP_CACHE  # preserve original path
    now = time.time()
    cache: Dict[str, Any] = {}

    # Try to load cache
    if cache_file.exists():
        try:
            cache = json.loads(cache_file.read_text())
        except Exception:
            cache = {}

    last_checked = float(cache.get("last_checked", 0) or 0)
    cached_ip = cache.get("ip", "Unavailable")

    # If last checked within 1 hour, return cached IP
    if now - last_checked < 3600 and cached_ip:
        return cached_ip

    # Otherwise, fetch new IP
    try:
        with urllib.request.urlopen("https://api.ipify.org", timeout=5) as response:
            ip = response.read().decode("utf8")
            cache = {"ip": ip, "last_checked": now}
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(json.dumps(cache))
            return ip
    except Exception:
        return cached_ip or "Unavailable"


def get_appliance_version() -> str:
    """Read the appliance version from the version file."""
    try:
        return APPLIANCE_VERSION_FILE.read_text().strip()
    except Exception:
        return "Unknown"


def _count_authorized_keys(path: Path) -> int:
    try:
        if not path.exists():
            return 0
        lines = path.read_text().splitlines()
        return sum(1 for raw in lines if (s := raw.strip()) and not s.startswith("#"))
    except Exception:
        return 0


def get_ssh_status() -> str:
    """Check if SSH is running and count authorized keys (colorized summary string preserved)."""
    # Check SSH service status
    try:
        result = subprocess.run(
            ["systemctl", "is-active", "ssh"],
            capture_output=True,
            text=True,
            check=False,
        )
        running = result.stdout.strip() == "active"
    except Exception:
        running = False

    # Count authorized keys
    auth_keys_path = Path.home() / ".ssh" / "authorized_keys"
    key_count = _count_authorized_keys(auth_keys_path)

    # Color logic and message format preserved
    color = Colors.GREEN if running and key_count > 0 else Colors.RED
    status = "Running" if running else "Stopped"
    return f"{color}SSH: {status} | Authorized Keys: {key_count}{Colors.NC}"


# -------------------------
# Machine identity helpers (API preserved)
# -------------------------

def _first_line(path: str) -> Optional[str]:
    """Return the first line of *path* or None if the file can’t be read."""
    try:
        return Path(path).read_text().splitlines()[0].strip()
    except Exception:
        return None


def make_appliance_id() -> str:
    """
    Combine the CPU ID and the Linux machine‑id into “<cpu‑id>-<machine‑id>” and return it.

    * CPU ID   → /sys/class/dmi/id/product_uuid
    * Host ID  → /etc/machine-id  (falls back to /var/lib/dbus/machine-id)
    """
    cpu_id = _first_line("/sys/class/dmi/id/product_uuid") or "unknown_cpu"
    host_id = (
        _first_line("/etc/machine-id")
        or _first_line("/var/lib/dbus/machine-id")
        or "unknown_host"
    )
    return f"{cpu_id}-{host_id}"
