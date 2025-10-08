"""
Shared DMS utility functions for NuNet menu system
"""

from __future__ import annotations

import json
import subprocess
from typing import Any, Dict, Iterable, List, Optional, Tuple

import os
from .utils import Colors  # kept even though display_peer_info receives Colors param


# -------------------------
# Internal helpers
# -------------------------

def _get_keyctl_passphrase(key_name: str = "dms_passphrase") -> Optional[str]:
    """
    Fetch a passphrase from the kernel keyring using keyctl.
    Returns the passphrase string or None if unavailable.
    """
    try:
        key_id_cp = subprocess.run(
            ["keyctl", "request", "user", key_name],
            capture_output=True,
            text=True,
            check=True,
        )
        key_id = key_id_cp.stdout.strip()
        if not key_id:
            return None

        pass_cp = subprocess.run(
            ["keyctl", "pipe", key_id],
            capture_output=True,
            text=True,
            check=True,
        )
        return pass_cp.stdout.strip() or None
    except subprocess.CalledProcessError:
        return None


# -------------------------
# Public functions
# -------------------------

def run_dms_command_with_passphrase(cmd: List[str], **kwargs) -> subprocess.CompletedProcess:
    """
    Run a DMS command with the DMS_PASSPHRASE environment variable set.
    The passphrase is fetched from the keyring only when needed and never stored.
    Behavior preserved: merges DMS_PASSPHRASE into env if available.
    """
    env = os.environ.copy()
    passphrase = _get_keyctl_passphrase("dms_passphrase")
    if passphrase:
        env["DMS_PASSPHRASE"] = passphrase

    # ensure env goes through but otherwise don't change caller's kwargs
    kwargs = dict(kwargs)
    kwargs["env"] = env
    return subprocess.run(cmd, **kwargs)


def display_peer_info(peer_info: Optional[Dict[str, Any]], Colors) -> None:
    """Display formatted peer information (output format preserved)."""
    if not peer_info:
        print(f"\n{Colors.RED}Error: Could not retrieve peer information{Colors.NC}")
        return

    print("\n=== Self Peer Information ===")
    print(f"Peer ID: {Colors.CYAN}{peer_info['peer_id']}{Colors.NC}")
    print(f"Context: {Colors.YELLOW}{peer_info['context']}{Colors.NC}")
    print(f"DID: {Colors.YELLOW}{peer_info['did']}{Colors.NC}\n")

    print("Network Addresses:")

    address_types: Iterable[Tuple[str, Iterable[str], str]] = [
        ("Local", peer_info["local_addrs"], Colors.CYAN),
        ("Public", peer_info["public_addrs"], Colors.GREEN),
        ("Relay", peer_info["relay_addrs"], Colors.YELLOW),
    ]

    for name, addresses, color in address_types:
        print(f"{color}{name}:{Colors.NC}")
        found = False
        for addr in addresses:
            print(f"  {addr}")
            found = True
        if not found:
            print("  None")
        print()

    print("Connection Summary:")
    if peer_info["is_relayed"]:
        print("• Using relay for all connections")
    else:
        if peer_info["public_addrs"]:
            print(f"• {Colors.GREEN}Direct public connection available{Colors.NC}")
        if peer_info["local_addrs"]:
            print(f"• {Colors.CYAN}Local network access available{Colors.NC}")
        if peer_info["relay_addrs"]:
            print(f"• {Colors.YELLOW}Relay connections available as backup{Colors.NC}")
    print()


def get_dms_status_info() -> Dict[str, Any]:
    """
    Returns a dict with the current DMS status, peer info, etc.
    Keys preserved:
      dms_status, dms_version, dms_running, dms_context, dms_did, dms_peer_id, dms_is_relayed
    """
    status: Dict[str, Any] = {
        "dms_status": "Unknown",
        "dms_version": "Unknown",
        "dms_running": "Not Running",
        "dms_context": "Unknown",
        "dms_did": "Unknown",
        "dms_peer_id": "Unknown",
        "dms_is_relayed": None,
    }

    # -- DMS version
    try:
        version_result = subprocess.run(
            ["nunet", "version"],
            capture_output=True,
            text=True,
            check=True,
        )
        for line in version_result.stdout.splitlines():
            if line.startswith("Version:"):
                status["dms_version"] = line.split()[1]
                status["dms_status"] = "Installed"
                break
    except Exception:
        pass  # keep Unknown/Not Installed states

    # -- Peer info + DID
    try:
        result = run_dms_command_with_passphrase(
            ["nunet", "-c", "dms", "actor", "cmd", "/dms/node/peers/self"],
            capture_output=True,
            text=True,
            check=True,
        )
        peer_info = json.loads(result.stdout)
        status["dms_running"] = "Running"
        status["dms_peer_id"] = peer_info.get("id", "Unknown")
        status["dms_context"] = "dms"

        did_result = run_dms_command_with_passphrase(
            ["nunet", "key", "did", "dms"],
            capture_output=True,
            text=True,
            check=True,
        )
        status["dms_did"] = did_result.stdout.strip()
    except Exception:
        status["dms_running"] = "Not Running"

    return status


def _bytes_to_gb(b: int, precision: int = 2) -> float:
    return round(b / (1024 ** 3), precision)


def _fmt_resources(resources_json: Dict[str, Any]) -> str:
    resources = resources_json.get("Resources", {})
    cpu_cores = resources.get("cpu", {}).get("cores", "N/A")
    ram_bytes = int(resources.get("ram", {}).get("size", 0) or 0)
    disk_bytes = int(resources.get("disk", {}).get("size", 0) or 0)
    ram_gb = _bytes_to_gb(ram_bytes)
    disk_gb = _bytes_to_gb(disk_bytes)
    return f"Cores: {cpu_cores}, RAM: {ram_gb} GB, Disk: {disk_gb} GB"


def get_dms_resource_info() -> Dict[str, str]:
    """
    Returns onboarding and resource info.
    Keys preserved:
      onboarding_status, free_resources, allocated_resources, onboarded_resources
    Values and color usage preserved.
    """
    info: Dict[str, str] = {}

    # --- Onboarding status ---
    onboarded = False
    try:
        onboarding_result = run_dms_command_with_passphrase(
            ["nunet", "-c", "dms", "actor", "cmd", "/dms/node/onboarding/status"],
            capture_output=True,
            text=True,
            check=True,
        )
        onboarding_json = json.loads(onboarding_result.stdout)
        onboarded = bool(onboarding_json.get("onboarded", False))
        info["onboarding_status"] = (
            f"{Colors.GREEN}ONBOARDED{Colors.NC}" if onboarded else f"{Colors.RED}NOT ONBOARDED{Colors.NC}"
        )
    except Exception:
        info["onboarding_status"] = f"{Colors.RED}Unknown (error){Colors.NC}"

    # --- Free resources ---
    if onboarded:
        try:
            resources_result = run_dms_command_with_passphrase(
                ["nunet", "-c", "dms", "actor", "cmd", "/dms/node/resources/free"],
                capture_output=True,
                text=True,
                check=True,
            )
            info["free_resources"] = _fmt_resources(json.loads(resources_result.stdout))
        except Exception:
            info["free_resources"] = "Unknown"
    else:
        info["free_resources"] = f"{Colors.RED}N/A (not onboarded){Colors.NC}"

    # --- Allocated resources ---
    if onboarded:
        try:
            allocated_result = run_dms_command_with_passphrase(
                ["nunet", "-c", "dms", "actor", "cmd", "/dms/node/resources/allocated"],
                capture_output=True,
                text=True,
                check=True,
            )
            info["allocated_resources"] = _fmt_resources(json.loads(allocated_result.stdout))
        except Exception:
            info["allocated_resources"] = "Unknown"
    else:
        info["allocated_resources"] = f"{Colors.RED}N/A (not onboarded){Colors.NC}"

    # --- Onboarded resources ---
    if onboarded:
        try:
            onboarded_result = run_dms_command_with_passphrase(
                ["nunet", "-c", "dms", "actor", "cmd", "/dms/node/resources/onboarded"],
                capture_output=True,
                text=True,
                check=True,
            )
            info["onboarded_resources"] = _fmt_resources(json.loads(onboarded_result.stdout))
        except Exception:
            info["onboarded_resources"] = "Unknown"
    else:
        info["onboarded_resources"] = f"{Colors.RED}N/A (not onboarded){Colors.NC}"

    return info
