"""
DMS (Device Management Service) management module
"""

from __future__ import annotations
import os
import json
import platform
import re
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, List
from datetime import datetime
from .utils import Colors, format_status
from .dms_utils import (
    run_dms_command_with_passphrase,
    get_dms_status_info,
    get_dms_resource_info,
)

# -------------------------
# Constants & configuration
# -------------------------

NUNET_SERVICE = "nunetdms"
KEYRING_SERVICES: Tuple[str, str] = ("loadubuntukeyring", "loadnunetkeyring")

DEFAULT_MENU_DIR = Path.home() / "menu"
DEFAULT_SCRIPTS_DIR = DEFAULT_MENU_DIR / "scripts"

CONFIGURE_DMS_SCRIPT = Path("/home/ubuntu/menu/scripts/configure-dms.sh")
ONBOARD_SCRIPT_NAME = "onboard-max.sh"

POLL_ATTEMPTS = 30
POLL_DELAY_SEC = 1.0


class DMSManager:
    """
    Facade for DMS control via 'nunet' CLI and systemd.
    Public method signatures and return shapes intentionally match the original
    implementation to avoid breaking callers.
    """

    def __init__(self, menu_dir: Optional[Path] = None, scripts_dir: Optional[Path] = None) -> None:
        self.menu_dir = menu_dir or DEFAULT_MENU_DIR
        candidate_scripts_dir = scripts_dir or (self.menu_dir / "scripts")

        # Prefer provided or default scripts dir, but fall back to repo's backend/scripts in dev
        onboard_script = candidate_scripts_dir / ONBOARD_SCRIPT_NAME
        if not onboard_script.exists():
            try:
                repo_scripts = Path(__file__).resolve().parents[1] / "scripts"
                repo_onboard = repo_scripts / ONBOARD_SCRIPT_NAME
                if repo_onboard.exists():
                    candidate_scripts_dir = repo_scripts
            except Exception:
                pass

        self.scripts_dir = candidate_scripts_dir

    # -------------------------
    # Private helper functions
    # -------------------------

    @staticmethod
    def _run(cmd: List[str], *, check: bool = False, capture: bool = True) -> subprocess.CompletedProcess:
        """
        Thin wrapper around subprocess.run with consistent defaults.
        """
        return subprocess.run(cmd, text=True, capture_output=capture, check=check)

    @staticmethod
    def _systemctl(*args: str, check: bool = True) -> subprocess.CompletedProcess:
        """
        Call systemctl with sudo, e.g., _systemctl('start', 'nunetdms').
        """
        return DMSManager._run(["sudo", "systemctl", *args], check=check)

    @staticmethod
    def _service_status(service: str) -> str:
        """
        Return 'systemctl status' output for a service without raising on non-zero status.
        """
        cp = DMSManager._systemctl("status", service, check=False)
        return cp.stdout

    @staticmethod
    def _wait_for_dms_ready(attempts: int = POLL_ATTEMPTS, delay_sec: float = POLL_DELAY_SEC) -> bool:
        """
        Poll 'nunet -c dms actor cmd /dms/node/peers/self' until it succeeds or attempts exhausted.
        """
        for _ in range(attempts):
            try:
                cp = run_dms_command_with_passphrase(
                    ["nunet", "-c", "dms", "actor", "cmd", "/dms/node/peers/self"],
                    capture_output=True,
                    text=True,
                    check=True,
                )
                # If check=True didn't raise, the command succeeded.
                return cp.returncode == 0
            except subprocess.CalledProcessError:
                time.sleep(delay_sec)
        return False

    @staticmethod
    def _package_url_for_arch(arch: str) -> Optional[str]:
        """
        Determine correct DMS package URL based on machine arch.
        """
        a = arch.lower()
        if "arm" in a or "aarch" in a:
            return "https://d.nunet.io/nunet-dms-arm64-latest.deb"
        if "x86_64" in a or "amd64" in a or "amd" in a:
            return "https://d.nunet.io/nunet-dms-amd64-latest.deb"
        return None

    @staticmethod
    def _categorize_addresses(listen_addrs_str: str) -> Tuple[List[str], List[str], List[str]]:
        """
        Split the comma+space delimited listen addresses and bucket them into local/public/relay.
        Mirrors original logic to preserve behavior.
        """
        listen_addrs = [a for a in listen_addrs_str.split(", ") if a]
        local: List[str] = []
        public: List[str] = []
        relay: List[str] = []

        for addr in listen_addrs:
            if "/p2p-circuit" in addr:
                relay.append(addr)
            elif any(p in addr for p in ["/ip4/127.", "/ip4/192.168.", "/ip4/10.", "/ip4/172."]):
                # Note: original used broad 172.* to match local; we keep that as-is.
                local.append(addr)
            else:
                public.append(addr)

        return local, public, relay

    # -------------------------
    # Public API
    # -------------------------

    def get_dms_version(self) -> str:
        """Get the DMS version from 'nunet version'."""
        try:
            result = self._run(["nunet", "version"], capture=True, check=True)
            # More robust parsing while keeping the same return values.
            # Expect lines like: "Version: 1.2.3"
            version_re = re.compile(r"^Version:\s*(\S+)")
            for line in result.stdout.splitlines():
                m = version_re.match(line.strip())
                if m:
                    return m.group(1)
        except (subprocess.CalledProcessError, FileNotFoundError):
            return "Not Installed"
        return "Unknown"

    def check_dms_installation(self) -> Dict[str, str]:
        """Check if DMS is installed and get its version."""
        try:
            self._run(["nunet", "version"], capture=True, check=True)
            version = self.get_dms_version()
            return {"status": "Installed", "version": version}
        except (subprocess.CalledProcessError, FileNotFoundError):
            return {"status": "Not Installed", "version": "N/A"}

    def restart_dms(self) -> Dict[str, str]:
        """Restart the DMS service and wait for it to be ready."""
        try:
            self._systemctl("stop", NUNET_SERVICE, check=True)
            self._systemctl("start", NUNET_SERVICE, check=True)
            status_out = self._service_status(NUNET_SERVICE)

            if self._wait_for_dms_ready():
                return {
                    "status": "success",
                    "message": "DMS service restarted and is fully operational\n" + status_out,
                }
            return {
                "status": "warning",
                "message": "DMS service restarted but may not be fully operational yet\n" + status_out,
            }
        except subprocess.CalledProcessError as e:
            return {"status": "error", "message": str(e)}

    def stop_dms(self) -> Dict[str, str]:
        """Stop the DMS service."""
        try:
            self._systemctl("stop", NUNET_SERVICE, check=True)
            status_out = self._service_status(NUNET_SERVICE)
            return {"status": "success", "message": status_out}
        except subprocess.CalledProcessError as e:
            return {"status": "error", "message": str(e)}

    def enable_dms(self) -> Dict[str, str]:
        """Enable DMS service and related services."""
        try:
            # Enable services
            for service in (*KEYRING_SERVICES, NUNET_SERVICE):
                self._systemctl("enable", service, check=True)

            # Start keyring services
            for service in KEYRING_SERVICES:
                self._systemctl("start", service, check=True)

            status_out = self._service_status(NUNET_SERVICE)
            return {"status": "success", "message": status_out}
        except subprocess.CalledProcessError as e:
            return {"status": "error", "message": str(e)}

    def disable_dms(self) -> Dict[str, str]:
        """Disable DMS service and related services."""
        try:
            for service in (NUNET_SERVICE, *reversed(KEYRING_SERVICES)):
                self._systemctl("disable", service, check=True)

            status_out = self._service_status(NUNET_SERVICE)
            return {"status": "success", "message": status_out}
        except subprocess.CalledProcessError as e:
            return {"status": "error", "message": str(e)}

    def get_peer_id(self) -> Optional[str]:
        """Get the peer ID."""
        try:
            result = run_dms_command_with_passphrase(
                ["nunet", "-c", "dms", "actor", "cmd", "/dms/node/peers/self"],
                capture_output=True,
                text=True,
                check=True,
            )
            data = json.loads(result.stdout)
            return data.get("id")
        except (subprocess.CalledProcessError, json.JSONDecodeError):
            return None

    def get_dms_status(self) -> str:
        """Get current DMS status ('Running' or 'Not Running')."""
        try:
            peer_id = self.get_peer_id()
            return "Running" if peer_id else "Not Running"
        except Exception:
            return "Not Running"

    def view_peer_details(self) -> Dict[str, str]:
        """View list of connected peers."""
        try:
            result = run_dms_command_with_passphrase(
                ["nunet", "-c", "dms", "actor", "cmd", "/dms/node/peers/list"],
                capture_output=True,
                text=True,
                check=True,
            )
            return {"status": "success", "message": result.stdout}
        except subprocess.CalledProcessError as e:
            return {"status": "error", "message": str(e)}

    def get_self_peer_info(self) -> Optional[Dict[str, Any]]:
        """Get self peer information including ID, context, DID and categorized listen addresses."""
        try:
            # Peer info (includes listen addresses)
            result = run_dms_command_with_passphrase(
                ["nunet", "-c", "dms", "actor", "cmd", "/dms/node/peers/self"],
                capture_output=True,
                text=True,
                check=True,
            )
            peer_info = json.loads(result.stdout)

            # DID for DMS context using keyring
            did_result = run_dms_command_with_passphrase(
                ["nunet", "key", "did", "dms"],
                capture_output=True,
                text=True,
                check=True,
            )
            did = did_result.stdout.strip()

            local_addrs, public_addrs, relay_addrs = self._categorize_addresses(
                peer_info.get("listen_addr", "")
            )

            return {
                "peer_id": peer_info.get("id", "Unknown"),
                "context": "dms",
                "did": did,
                "local_addrs": local_addrs,
                "public_addrs": public_addrs,
                "relay_addrs": relay_addrs,
                "is_relayed": len(relay_addrs) > 0 and len(public_addrs) == 0,
            }
        except subprocess.CalledProcessError as e:
            print(f"Error executing command: {e.stderr}")
            return None
        except json.JSONDecodeError as e:
            print(f"Error parsing JSON response: {e}")
            return None
        except Exception as e:
            print(f"Unexpected error: {e}")
            return None

    def onboard_compute(self) -> Dict[str, str]:
        """Onboard compute resources via onboard-max.sh."""
        try:
            script_path = self.scripts_dir / ONBOARD_SCRIPT_NAME
            if not script_path.exists():
                return {"status": "error", "message": f"Script not found at {script_path}"}

            run_dms_command_with_passphrase([str(script_path)], check=True)
            return {"status": "success", "message": "Compute resources onboarded successfully"}
        except subprocess.CalledProcessError as e:
            return {"status": "error", "message": f"Error during compute onboarding: {str(e)}"}

    def offboard_compute(self) -> Dict[str, str]:
        """Offboard compute resources."""
        try:
            result = run_dms_command_with_passphrase(
                ["nunet", "-c", "dms", "actor", "cmd", "/dms/node/onboarding/offboard"],
                capture_output=True,
                text=True,
                check=True,
            )
            return {"status": "success", "message": result.stdout}
        except subprocess.CalledProcessError as e:
            return {"status": "error", "message": str(e)}

    def get_resource_allocation(self) -> Dict[str, str]:
        """Get current resource allocation."""
        try:
            result = run_dms_command_with_passphrase(
                ["nunet", "-c", "dms", "actor", "cmd", "/dms/node/resources/allocated"],
                capture_output=True,
                text=True,
                check=True,
            )
            return {"status": "success", "message": result.stdout}
        except subprocess.CalledProcessError as e:
            return {"status": "error", "message": str(e)}

    def initialize_dms(self) -> Dict[str, str]:
        """Initialize the DMS system."""
        try:
            script_path = CONFIGURE_DMS_SCRIPT
            if not script_path.exists():
                return {"status": "error", "message": f"Script not found at {script_path}"}

            try:
                # Show real-time progress (no capture)
                run_dms_command_with_passphrase(["sudo", "-u", "ubuntu", str(script_path)], check=True)
                return {"status": "success", "message": "DMS initialization completed successfully"}
            except KeyboardInterrupt:
                return {"status": "error", "message": "DMS initialization was interrupted by user"}
        except subprocess.CalledProcessError as e:
            return {"status": "error", "message": f"Error during DMS initialization: {str(e)}"}

    def update_dms(self) -> Dict[str, str]:
        """Update DMS to latest version."""
        try:
            arch = platform.machine().lower()
            print(f"🖥️  Detected architecture: {arch}")

            url = self._package_url_for_arch(arch)
            if not url:
                return {"status": "error", "message": f"❌ Unsupported architecture: {arch}"}

            print(f"⬇️  Downloading latest DMS package from {url}...")
            download = self._run(["wget", "-N", url, "-O", "dms-latest.deb"], capture=True, check=False)
            if download.returncode != 0:
                return {"status": "error", "message": f"❌ Download failed: {download.stderr}"}

            print("🔄 Installing updated DMS...")
            install = self._run(
                ["sudo", "apt", "install", "./dms-latest.deb", "-y", "--allow-downgrades"],
                capture=True,
                check=False,
            )
            if install.returncode == 0:
                # Match original behavior: remove deb only on success
                self._run(["rm", "-f", "dms-latest.deb"], check=False)
                return {"status": "success", "message": "✅ DMS updated successfully!"}
            return {"status": "error", "message": f"❌ Installation failed: {install.stderr}"}

        except subprocess.CalledProcessError as e:
            return {"status": "error", "message": f"⚠️  Critical error during update:  {str(e)}"}

    def update_dms_status(self) -> Dict[str, Any]:
        """
        Update and return the current DMS status information.
        Returns a dictionary with all relevant DMS status fields.
        """
        status: Dict[str, Any] = {
            "dms_status": "Unknown",
            "dms_version": "Unknown",
            "dms_running": format_status("Not Running"),
            "dms_context": "Unknown",
            "dms_did": "Unknown",
            "dms_peer_id": "Unknown",
            "dms_is_relayed": None,
        }

        # Installation + version
        install_check = self.check_dms_installation()
        status["dms_status"] = install_check["status"]
        status["dms_version"] = install_check["version"]

        # Try to enrich with live peer info
        try:
            peer_info = self.get_self_peer_info()
            if peer_info and "error" not in peer_info:
                status["dms_running"] = format_status("Running")
                status["dms_peer_id"] = peer_info["peer_id"]
                status["dms_context"] = peer_info["context"]
                status["dms_did"] = peer_info["did"]
                status["dms_is_relayed"] = peer_info["is_relayed"]
        except Exception:
            status["dms_running"] = format_status("Not Running")

        return status

    def get_full_status_info(self) -> Dict[str, Any]:
        """
        Merge basic DMS status with resource info (original behavior preserved).
        """
        status = get_dms_status_info()
        resources = get_dms_resource_info()
        return {**status, **resources}

    def show_full_status(self) -> None:
        """
        Print a colorized, human-readable status summary (unchanged behavior).
        """
        full_status = self.get_full_status_info()
        print("\n=== DMS Full Status ===")
        print(f"Onboarding Status: {full_status.get('onboarding_status', 'Unknown')}")
        print(f"Free Resources: {full_status.get('free_resources', 'Unknown')}")
        print(f"Allocated Resources: {full_status.get('allocated_resources', 'Unknown')}")
        print(f"Onboarded Resources: {full_status.get('onboarded_resources', 'Unknown')}")
        print(
            f"DMS Status: {full_status['dms_status']} (v{full_status['dms_version']}) "
            f"{full_status['dms_running']} Context: {Colors.YELLOW}{full_status['dms_context']}{Colors.NC} "
        )
        if full_status["dms_peer_id"] != "Unknown":
            print(f"DMS DID: {Colors.YELLOW}{full_status['dms_did']}{Colors.NC}")
            print(f"DMS Peer ID: {Colors.CYAN}{full_status['dms_peer_id']}{Colors.NC}")
            if full_status["dms_is_relayed"] is not None:
                relay_status = "Using relay" if full_status["dms_is_relayed"] else "Direct connection"
                relay_color = Colors.YELLOW if full_status["dms_is_relayed"] else Colors.GREEN
                print(f"NuNet Network Connection Type: {relay_color}{relay_status}{Colors.NC}")

    def confirm_transaction(self, unique_id: str, tx_hash: str) -> Dict[str, Any]:
        """
        Call DMS to confirm a transaction:
        nunet actor cmd --context user /dms/tokenomics/contract/transactions/confirm
          --unique-id <uniqueid> --tx-hash <txhash>
        Uses keyring-backed passphrase via run_dms_command_with_passphrase.
        """
        try:
            cp = run_dms_command_with_passphrase(
                [
                    "nunet", "actor", "cmd", "--context", "user",
                    "/dms/tokenomics/contract/transactions/confirm",
                    "--unique-id", unique_id,
                    "--tx-hash", tx_hash,
                ],
                capture_output=True,
                text=True,
                check=True,
            )
            return {"status": "success", "stdout": cp.stdout.strip(), "stderr": cp.stderr.strip()}
        except subprocess.CalledProcessError as e:
            return {"status": "error", "message": e.stderr or str(e)}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def list_transactions(self) -> Dict[str, Any]:
        """
        Call DMS to list transactions:
        nunet actor cmd --context user /dms/tokenomics/contract/transactions/list
        Expects JSON on stdout with shape: { "transactions": [ ... ] }
        """
        # for now we return mock data below
        # --------------------------from here========================
        return { 
        "transactions": [
            {
            "UniqueID": "inv_001",
            "PaymentValidatorDID": "did:nunet:validator:123456789abcdef",
            "ContractDID": "did:nunet:contract:987654321abcdef",
            "ToAddress": "0x1111111111111111111111111111111111111111",
            "Amount": "25",
            "Status": "paid",
            "TxHash": ""
            },
            {
            "UniqueID": "inv_002",
            "PaymentValidatorDID": "did:nunet:validator:abcdef987654321",
            "ContractDID": "did:nunet:contract:abcdef123456789",
            "ToAddress": "0x2222222222222222222222222222222222222222",
            "Amount": "0.5",
            "Status": "unpaid",
            "TxHash": ""
            },
            {
            "UniqueID": "inv_003",
            "PaymentValidatorDID": "did:nunet:validator:1122334455667788",
            "ContractDID": "did:nunet:contract:8877665544332211",
            "ToAddress": "0x3333333333333333333333333333333333333333",
            "Amount": "100",
            "Status": "paid",
            "TxHash": ""
            }
        ]
        }

        # --------------------------from here========================

        #TODO uncomment below when DMS we have the newst DMS on the appliance
        # try:
        #     cp = run_dms_command_with_passphrase(
        #         [
        #             "nunet", "actor", "cmd", "--context", "user",
        #             "/dms/tokenomics/contract/transactions/list",
        #         ],
        #         capture_output=True,
        #         text=True,
        #         check=True,
        #     )
        #     out = cp.stdout.strip() or "{}"
        #     data = json.loads(out)
        #     txs = data.get("transactions", [])
        #     return {"status": "success", "transactions": txs}
        # except subprocess.CalledProcessError as e:
        #     return {"status": "error", "message": e.stderr or str(e)}
        # except json.JSONDecodeError:
        #     return {"status": "error", "message": "Invalid JSON from DMS /transactions/list"}
        # except Exception as e:
        #     return {"status": "error", "message": str(e)}
    
    def get_structured_logs(self, alloc_dir: Optional[Path] = None, *, lines: int = 200) -> Dict[str, Any]:
        """
        Return structured logs:
          - allocation stdout/stderr (tail of files) if alloc_dir given
          - DMS service logs from journalctl
        Does not affect the menu; purely read-only helpers.
        """
        result: Dict[str, Any] = {
            "status": "success",
            "message": "Structured logs fetched",
            "allocation": None,
            "dms_logs": None,
        }

        # DMS service logs
        result["dms_logs"] = _journalctl_dms(lines)

        # Allocation logs (optional)
        if alloc_dir:
            base = Path("/home/nunet/nunet/deployments")
            alloc_path = Path(alloc_dir)
            if not _safe_under(base, alloc_path):
                return {
                    "status": "error",
                    "message": f"alloc_dir must live under {base}",
                    "dms_logs": result["dms_logs"],
                    "allocation": None,
                }

            stdout_path = alloc_path / "stdout.logs"
            stderr_path = alloc_path / "stderr.logs"
            result["allocation"] = {
                "dir": str(alloc_path),
                "stdout": _make_filelog(stdout_path, lines),
                "stderr": _make_filelog(stderr_path, lines),
            }

            # if both files missing, downgrade message
            a = result["allocation"]
            if not a["stdout"]["exists"] and not a["stderr"]["exists"]:
                result["message"] = "Structured logs fetched (allocation files not found)"

        return result


def _to_iso(ts: float) -> str:
    try:
        return datetime.utcfromtimestamp(ts).isoformat() + "Z"
    except Exception:
        return None

def _run_capture(argv: list[str], env: dict | None = None, cwd: str | None = None, timeout: int = 30):
    return subprocess.run(
        argv,
        text=True,
        capture_output=True,
        env=env,
        cwd=cwd,
        timeout=timeout,
        check=False,
    )

def _safe_under(base: Path, child: Path) -> bool:
    try:
        return str(child.resolve()).startswith(str(base.resolve()))
    except Exception:
        return False

def _stat_file_with_sudo(path: Path) -> tuple[Optional[int], Optional[str], Optional[str]]:
    """
    Return (size_bytes, mtime_iso, err). Uses sudo stat to tolerate perms.
    """
    cp = _run_capture(["sudo", "-n", "stat", "-c", "%s,%Y", str(path)])
    if cp.returncode == 0:
        try:
            size_s, mtime_s = (cp.stdout.strip() or "").split(",", 1)
            size = int(size_s)
            mtime_iso = _to_iso(float(mtime_s))
            return size, mtime_iso, None
        except Exception as e:
            return None, None, f"stat parse error: {e}"
    else:
        return None, None, (cp.stderr or cp.stdout or "").strip() or "stat failed"

def _tail_file_with_sudo(path: Path, lines: int) -> tuple[str, bool, Optional[str]]:
    """
    Return (content, readable, err). Uses sudo tail -n <lines>.
    """
    cp = _run_capture(["sudo", "-n", "tail", "-n", str(lines), str(path)])
    if cp.returncode == 0:
        return cp.stdout, True, None
    else:
        err = (cp.stderr or cp.stdout or "").strip() or f"tail failed rc={cp.returncode}"
        return "", False, err

def _make_filelog(path: Path, lines: int) -> dict:
    exists = path.exists()
    size, mtime_iso, stat_err = (None, None, None)
    content, readable, read_err = ("", False, None)

    if exists:
        size, mtime_iso, stat_err = _stat_file_with_sudo(path)
        content, readable, read_err = _tail_file_with_sudo(path, lines)

    error = None
    if not exists:
        error = "file not found"
    elif not readable:
        error = read_err or stat_err
    elif stat_err:
        # readable but stat had a warning
        error = stat_err

    return {
        "path": str(path),
        "exists": exists,
        "readable": readable,
        "size_bytes": size,
        "mtime_iso": mtime_iso,
        "tail_lines": lines,
        "content": content if readable else None,
        "error": error,
    }

def _journalctl_dms(lines: int) -> dict:
    cp = _run_capture([
        "sudo", "-n", "journalctl", "-u", "nunetdms",
        "-n", str(lines), "--no-pager", "--output=short-iso"
    ], timeout=60)
    return {
        "source": "journalctl",
        "lines": lines,
        "stdout": cp.stdout or "",
        "stderr": cp.stderr or "",
        "returncode": cp.returncode,
    }

