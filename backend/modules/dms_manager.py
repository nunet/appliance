"""
Device Management Service (DMS) management helpers.
"""

import json
import logging
import math
import os
import platform
import shutil
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from .environment_profile import (
    get_runtime_profile,
    iter_package_candidates,
    normalize_arch,
)
from .dms_utils import (
    run_dms_command_with_passphrase,
    categorize_listen_addresses,
    DmsCommandResult,
    contract_approve_local,
    contract_create,
    contract_list_incoming,
    contract_list_outgoing,
    contract_terminate,
    contract_state,
)
from .path_constants import (
    BACKEND_DIR,
    DMS_DEPLOYMENTS_DIR,
    DMS_DEPLOYMENTS_LOGS,
    DMS_LOG_JSONL_PATH,
    DMS_LOG_PATH,
    NUNET_CONFIG_PATH,
)

logger = logging.getLogger(__name__)

NUNET_SERVICE = "nunetdms"
ONBOARD_SCRIPT_NAME = "onboard-max.sh"

DEFAULT_SCRIPTS_DIR = BACKEND_DIR / "scripts"

POLL_ATTEMPTS = 30
POLL_DELAY_SEC = 1.0

SUPPORTED_BLOCKCHAINS = {"ETHEREUM", "CARDANO"}
DEFAULT_BLOCKCHAIN = "ETHEREUM"


class DMSManager:
    """Helpers for interacting with the DMS via the nunet CLI and systemd."""

    _INCOMING_STATES = {"DRAFT", "PENDING", "INCOMING"}
    _ACTIVE_STATES = {"ACCEPTED", "APPROVED", "SIGNED"}
    _SIGNED_STATES = set(_ACTIVE_STATES) | {"COMPLETED", "SETTLED", "TERMINATED"}

    def __init__(self, menu_dir: Optional[Path] = None, scripts_dir: Optional[Path] = None) -> None:
        # menu_dir retained only for backward compatibility; scripts now live under backend/scripts
        candidate_scripts_dir = scripts_dir or DEFAULT_SCRIPTS_DIR
        if not (candidate_scripts_dir / ONBOARD_SCRIPT_NAME).exists():
            try:
                repo_scripts = Path(__file__).resolve().parents[1] / "scripts"
                if (repo_scripts / ONBOARD_SCRIPT_NAME).exists():
                    candidate_scripts_dir = repo_scripts
            except Exception as exc:
                logger.debug("Unable to resolve repository scripts directory: %s", exc)

        self.scripts_dir = candidate_scripts_dir
        logger.debug("Using scripts directory: %s", self.scripts_dir)

    @staticmethod
    def _contract_command_metadata(result: DmsCommandResult) -> Dict[str, Any]:
        command = None
        if result.get("argv"):
            command = " ".join(result["argv"])  # type: ignore[index]
        return {
            "stdout": result.get("stdout", ""),
            "stderr": result.get("stderr", ""),
            "returncode": result.get("returncode"),
            "command": command,
        }

    @classmethod
    def _contract_error(cls, result: DmsCommandResult, fallback: str) -> Dict[str, Any]:
        message = result.get("error") or fallback
        endpoint = result.get("endpoint", "contract command")
        logger.error("%s failed: %s", endpoint, message)
        response = {"status": "error", "message": message}
        response.update(cls._contract_command_metadata(result))
        return response

    @classmethod
    def _contract_success(cls, result: DmsCommandResult, payload: Dict[str, Any]) -> Dict[str, Any]:
        response = {"status": "success"}
        response.update(payload)
        response.update(cls._contract_command_metadata(result))
        return response

    @staticmethod
    def _run(
        cmd: List[str],
        *,
        check: bool = False,
        capture: bool = True,
        timeout: Optional[int] = None,
        env: Optional[Dict[str, str]] = None,
    ) -> subprocess.CompletedProcess:
        logger.debug("Executing command: %s", " ".join(cmd))
        return subprocess.run(
            cmd,
            text=True,
            capture_output=capture,
            check=check,
            timeout=timeout,
            env=env,
        )

    @staticmethod
    def _systemctl(*args: str, check: bool = True) -> subprocess.CompletedProcess:
        return DMSManager._run(["sudo", "systemctl", *args], check=check)

    @staticmethod
    def _service_status(service: str) -> str:
        cp = DMSManager._systemctl("status", service, check=False)
        return cp.stdout or ""

    @staticmethod
    def _wait_for_dms_ready(attempts: int = POLL_ATTEMPTS, delay_sec: float = POLL_DELAY_SEC) -> bool:
        for attempt in range(1, attempts + 1):
            cp = run_dms_command_with_passphrase(
                ["nunet", "-c", "dms", "actor", "cmd", "/dms/node/peers/self"],
                capture_output=True,
                text=True,
                check=False,
            )
            if cp.returncode == 0:
                logger.debug("DMS readiness confirmed after %s attempt(s)", attempt)
                return True
            logger.debug(
                "DMS readiness probe failed (attempt %s/%s, rc=%s)",
                attempt,
                attempts,
                cp.returncode,
            )
            time.sleep(delay_sec)
        logger.warning("Timed out waiting for DMS readiness after %s attempts", attempts)
        return False

    @staticmethod
    def _package_candidates_for_arch(arch: str) -> List[Tuple[str, str]]:
        normalized_arch = normalize_arch(arch)
        if not normalized_arch:
            return []
        policy = get_runtime_profile().dms_updates
        return [(channel, url) for channel, url in iter_package_candidates("dms", normalized_arch, policy)]

    @staticmethod
    def _extract_version(output: str) -> Optional[str]:
        for line in (output or "").splitlines():
            line = line.strip()
            if not line:
                continue
            if line.lower().startswith("version"):
                parts = line.split(":", 1)
                if len(parts) == 2:
                    return parts[1].strip()
                tokens = line.split()
                if tokens:
                    return tokens[-1]
        return None

    def get_dms_version(self) -> str:
        try:
            cp = self._run(["nunet", "version"], capture=True, check=False)
        except FileNotFoundError:
            logger.warning("nunet CLI not available while checking version")
            return "Not Installed"
        if cp.returncode != 0:
            logger.debug("nunet version failed rc=%s: %s", cp.returncode, cp.stderr or cp.stdout or "")
            return "Not Installed"
        version = self._extract_version(cp.stdout or "")
        return version or "Unknown"

    def check_dms_installation(self) -> Dict[str, str]:
        try:
            cp = self._run(["nunet", "version"], capture=True, check=False)
        except FileNotFoundError:
            logger.debug("nunet CLI not found while checking installation status")
            return {"status": "Not Installed", "version": "N/A"}
        if cp.returncode != 0:
            logger.debug("DMS not installed or nunet CLI unavailable: rc=%s", cp.returncode)
            return {"status": "Not Installed", "version": "N/A"}
        version = self._extract_version(cp.stdout or "") or "Unknown"
        return {"status": "Installed", "version": version}

    def restart_dms(self) -> Dict[str, str]:
        try:
            self._systemctl("stop", NUNET_SERVICE, check=True)
            self._systemctl("start", NUNET_SERVICE, check=True)
            status_out = self._service_status(NUNET_SERVICE)
            if self._wait_for_dms_ready():
                return {
                    "status": "success",
                    "message": "DMS service restarted and is operational.\n" + status_out,
                }
            return {
                "status": "warning",
                "message": "DMS service restarted but readiness probe failed.\n" + status_out,
            }
        except subprocess.CalledProcessError as exc:
            logger.error("Failed to restart DMS: %s", exc)
            return {"status": "error", "message": str(exc)}

    def get_peer_id(self) -> Optional[str]:
        cp = run_dms_command_with_passphrase(
            ["nunet", "-c", "dms", "actor", "cmd", "/dms/node/peers/self"],
            capture_output=True,
            text=True,
            check=False,
        )
        if cp.returncode != 0 or not cp.stdout:
            logger.debug("Failed to fetch peer id: rc=%s, stderr=%s", cp.returncode, cp.stderr or "")
            return None
        try:
            payload = json.loads(cp.stdout)
        except json.JSONDecodeError as exc:
            logger.warning("Invalid JSON while reading peer id: %s", exc)
            return None
        return payload.get("id") or payload.get("peer_id")

    def get_dms_status(self) -> str:
        return "Running" if self.get_peer_id() else "Not Running"

    def view_peer_details(self) -> Dict[str, str]:
        cp = run_dms_command_with_passphrase(
            ["nunet", "-c", "dms", "actor", "cmd", "/dms/node/peers/list"],
            capture_output=True,
            text=True,
            check=False,
        )
        if cp.returncode == 0:
            return {"status": "success", "message": cp.stdout or ""}
        message = cp.stderr or cp.stdout or f"Command failed with return code {cp.returncode}"
        logger.debug("Failed to list peers: %s", message)
        return {"status": "error", "message": message}

    def get_self_peer_info(self) -> Optional[Dict[str, Any]]:
        cp = run_dms_command_with_passphrase(
            ["nunet", "-c", "dms", "actor", "cmd", "/dms/node/peers/self"],
            capture_output=True,
            text=True,
            check=False,
        )
        if cp.returncode != 0 or not cp.stdout:
            logger.debug("Failed to fetch self peer info: rc=%s, stderr=%s", cp.returncode, cp.stderr or "")
            return None
        try:
            payload = json.loads(cp.stdout)
        except json.JSONDecodeError as exc:
            logger.warning("Invalid self peer JSON: %s", exc)
            return None

        local_addrs, public_addrs, relay_addrs = categorize_listen_addresses(payload.get("listen_addr"))

        did_cp = run_dms_command_with_passphrase(
            ["nunet", "key", "did", "dms"],
            capture_output=True,
            text=True,
            check=False,
        )
        did = did_cp.stdout.strip() if did_cp.returncode == 0 and did_cp.stdout else "Unknown"
        if did_cp.returncode != 0:
            logger.debug("Failed to read DMS DID: rc=%s, stderr=%s", did_cp.returncode, did_cp.stderr or "")

        return {
            "peer_id": payload.get("id") or payload.get("peer_id") or "Unknown",
            "context": payload.get("context") or "dms",
            "did": did,
            "local_addrs": local_addrs,
            "public_addrs": public_addrs,
            "relay_addrs": relay_addrs,
            "is_relayed": bool(relay_addrs and not public_addrs),
        }

    @staticmethod
    def _calculate_onboard_resources() -> Dict[str, Any]:
        """
        Calculate CPU, RAM, Disk, and GPU resources for onboarding.
        Uses /dms/node/hardware/spec endpoint for hardware information.
        Replicates the logic from onboard-max.sh bash script.
        """
        resources: Dict[str, Any] = {
            "cpu_cores": 1,
            "ram_gb": 0.0,
            "disk_gb": 0.0,
            "gpus": [],  # List of (index, vram_gb) tuples for all detected GPUs
        }

        # Get hardware specification from DMS
        hardware_spec = None
        try:
            logger.info("Querying hardware spec from DMS: /dms/node/hardware/spec")
            cp = run_dms_command_with_passphrase(
                ["nunet", "-c", "dms", "actor", "cmd", "/dms/node/hardware/spec"],
                capture_output=True,
                text=True,
                check=False,
            )
            if cp.returncode == 0 and cp.stdout:
                try:
                    hardware_spec = json.loads(cp.stdout)
                    logger.info("Hardware spec retrieved successfully: %s", json.dumps(hardware_spec, indent=2))
                except json.JSONDecodeError as exc:
                    logger.warning("Failed to parse hardware spec JSON: %s. Raw output: %s", exc, cp.stdout[:200])
            else:
                logger.warning("Failed to get hardware spec: rc=%s, stdout=%s, stderr=%s", 
                             cp.returncode, cp.stdout or "", cp.stderr or "")
        except Exception as exc:
            logger.warning("Failed to query hardware spec: %s", exc, exc_info=True)

        # 1) CPU: total cores minus 1 (minimum 1)
        try:
            # Check multiple possible response structures
            cpu_cores = None
            if hardware_spec:
                # Try different response formats
                if hardware_spec.get("OK") and hardware_spec.get("Resources", {}).get("cpu"):
                    cpu_cores = hardware_spec["Resources"]["cpu"].get("cores", 0)
                    logger.info("Using CPU cores from hardware spec (OK format): %s", cpu_cores)
                elif hardware_spec.get("Resources", {}).get("cpu"):
                    cpu_cores = hardware_spec["Resources"]["cpu"].get("cores", 0)
                    logger.info("Using CPU cores from hardware spec (no OK key): %s", cpu_cores)
                elif "cpu" in hardware_spec:
                    cpu_cores = hardware_spec["cpu"].get("cores", 0) if isinstance(hardware_spec["cpu"], dict) else None
                    if cpu_cores:
                        logger.info("Using CPU cores from hardware spec (flat format): %s", cpu_cores)
            
            if cpu_cores is None or cpu_cores == 0:
                # Fallback to os.cpu_count()
                cpu_cores = os.cpu_count() or 1
                logger.info("Using fallback CPU count: %s", cpu_cores)
            
            cpu_onboard = max(1, cpu_cores - 1)
            resources["cpu_cores"] = cpu_onboard
            logger.info("Final CPU cores to onboard: %s", cpu_onboard)
        except Exception as exc:
            logger.warning("Failed to determine CPU cores: %s", exc, exc_info=True)

        # 2) RAM in GiB
        #    - Total from hardware spec (bytes) -> GiB, or fallback to /proc/meminfo
        #    - Used from "free -k" (KiB) -> GiB
        #    - Free = (Total - Used)
        #    - Floor free RAM to nearest 0.5 GiB
        #    - Onboard RAM = min(floored free RAM, 89% of total)
        try:
            # Get total RAM from hardware spec or fallback to /proc/meminfo
            total_ram_gb = None
            if hardware_spec:
                # Try different response formats
                if hardware_spec.get("OK") and hardware_spec.get("Resources", {}).get("ram"):
                    ram_bytes = hardware_spec["Resources"]["ram"].get("size", 0)
                    if ram_bytes > 0:
                        total_ram_gb = ram_bytes / (1024 ** 3)
                        logger.info("Using RAM from hardware spec (OK format): %.2f GiB", total_ram_gb)
                elif hardware_spec.get("Resources", {}).get("ram"):
                    ram_bytes = hardware_spec["Resources"]["ram"].get("size", 0)
                    if ram_bytes > 0:
                        total_ram_gb = ram_bytes / (1024 ** 3)
                        logger.info("Using RAM from hardware spec (no OK key): %.2f GiB", total_ram_gb)
                elif "ram" in hardware_spec:
                    ram_data = hardware_spec["ram"]
                    if isinstance(ram_data, dict):
                        ram_bytes = ram_data.get("size", 0)
                        if ram_bytes > 0:
                            total_ram_gb = ram_bytes / (1024 ** 3)
                            logger.info("Using RAM from hardware spec (flat format): %.2f GiB", total_ram_gb)
            
            if total_ram_gb is None:
                # Fallback to /proc/meminfo
                logger.info("Using fallback RAM calculation from /proc/meminfo")
                with open("/proc/meminfo", "r") as f:
                    for line in f:
                        if line.startswith("MemTotal:"):
                            total_ram_kb = int(line.split()[1])
                            total_ram_gb = total_ram_kb / 1048576.0
                            logger.info("Total RAM from /proc/meminfo: %.2f GiB", total_ram_gb)
                            break
                    else:
                        raise ValueError("MemTotal not found in /proc/meminfo")

            # Get current used RAM from "free -k"
            free_cp = subprocess.run(
                ["free", "-k"],
                capture_output=True,
                text=True,
                check=False,
            )
            if free_cp.returncode == 0 and total_ram_gb is not None:
                for line in free_cp.stdout.splitlines():
                    if line.startswith("Mem:"):
                        parts = line.split()
                        if len(parts) >= 3:
                            current_ram_used_kb = int(parts[2])
                            current_ram_used_gb = current_ram_used_kb / 1048576.0
                            free_ram_gb = total_ram_gb - current_ram_used_gb

                            # Floor free RAM to the nearest 0.5 GiB
                            floored_free_ram_gb = math.floor(free_ram_gb * 2) / 2.0
                            if floored_free_ram_gb < 0:
                                floored_free_ram_gb = 0.0

                            # 89% of total RAM
                            ram_89_percent_gb = total_ram_gb * 0.89

                            # Choose the smaller value
                            ram_onboard_gb = min(floored_free_ram_gb, ram_89_percent_gb)
                            resources["ram_gb"] = round(ram_onboard_gb, 1)
                            break
        except Exception as exc:
            logger.warning("Failed to calculate RAM: %s", exc)

        # 3) Disk in GiB
        #    - Use df -k on a single path (root) so we get free space on the filesystem
        #      DMS actually uses. df --total would sum "Available" across all mounts,
        #      which can over-report and cause "not enough free Disk" from DMS.
        #    - Convert KiB -> GiB, subtract 5 GiB reserve.
        try:
            df_path = "/"
            df_cp = subprocess.run(
                ["df", "-k", df_path],
                capture_output=True,
                text=True,
                check=False,
            )
            if df_cp.returncode == 0:
                lines = df_cp.stdout.strip().splitlines()
                # First data line (after header) is for df_path
                if len(lines) >= 2:
                    data_line = lines[1]
                    parts = data_line.split()
                    # Columns: Filesystem, 1K-blocks, Used, Available, Use%, Mounted on
                    if len(parts) >= 4:
                        free_disk_kb = int(parts[3])
                        free_disk_gb = free_disk_kb / 1048576.0
                        disk_onboard_gb = max(0.0, free_disk_gb - 5.0)
                        resources["disk_gb"] = round(disk_onboard_gb, 2)
                        logger.info(
                            "Disk from df -k %s: free=%.2f GiB, onboard=%.2f GiB (after 5 GiB reserve)",
                            df_path,
                            free_disk_gb,
                            resources["disk_gb"],
                        )
        except Exception as exc:
            logger.warning("Failed to calculate disk space: %s", exc)

        # 4) GPU selection
        #    - Get GPU info from hardware spec JSON
        #    - Detect ALL GPUs reported
        #    - Allocate 80% of each GPU's VRAM
        #    - If GPUs are detected, we MUST onboard them (specify them exactly)
        try:
            gpus = None
            if hardware_spec:
                # Try different response formats
                if hardware_spec.get("OK") and hardware_spec.get("Resources", {}).get("gpus"):
                    gpus = hardware_spec["Resources"]["gpus"]
                    logger.info("Found GPUs in hardware spec (OK format): %s", gpus)
                elif hardware_spec.get("Resources", {}).get("gpus"):
                    gpus = hardware_spec["Resources"]["gpus"]
                    logger.info("Found GPUs in hardware spec (no OK key): %s", gpus)
                elif "gpus" in hardware_spec:
                    gpus = hardware_spec["gpus"]
                    logger.info("Found GPUs in hardware spec (flat format): %s", gpus)
            
            if gpus and isinstance(gpus, list):
                for gpu in gpus:
                    try:
                        gpu_index = gpu.get("index")
                        vram_bytes = gpu.get("vram", 0)
                        
                        if gpu_index is not None and vram_bytes > 0:
                            # Convert VRAM from bytes to GiB, then calculate 80%, minimum 1 GiB
                            vram_gb = vram_bytes / (1024 ** 3)
                            gpu_vram_onboard_gb = max(1, int(vram_gb * 0.8))
                            resources["gpus"].append((gpu_index, gpu_vram_onboard_gb))
                            logger.info("Detected GPU: index=%s, vram_bytes=%s, vram_gb=%.2f, onboard_gb=%s", 
                                       gpu_index, vram_bytes, vram_gb, gpu_vram_onboard_gb)
                        else:
                            logger.debug("Skipping GPU entry with missing index or vram: %s", gpu)
                    except (ValueError, TypeError) as exc:
                        logger.warning("Failed to parse GPU entry '%s': %s", gpu, exc)
            else:
                if gpus is not None:
                    logger.debug("GPUs not in expected list format: %s (type: %s)", gpus, type(gpus))
                else:
                    logger.debug("No GPU entries found in hardware spec")
        except Exception as exc:
            logger.warning("Failed to process GPU info from hardware spec: %s", exc, exc_info=True)

        return resources

    def onboard_compute(self) -> Dict[str, str]:
        """
        Onboard compute resources using calculated values.
        Replaces the bash script onboard-max.sh with Python implementation.
        """
        try:
            # Calculate resources
            resources = self._calculate_onboard_resources()

            # Build the nunet command
            cmd = [
                "nunet",
                "-c",
                "dms",
                "actor",
                "cmd",
                "/dms/node/onboarding/onboard",
                "--disk",
                str(resources["disk_gb"]),
                "--ram",
                str(resources["ram_gb"]),
                "--cpu",
                str(resources["cpu_cores"]),
            ]

            # Add GPU args for ALL detected GPUs (must specify them exactly)
            if resources["gpus"]:
                for gpu_index, gpu_vram_gb in resources["gpus"]:
                    cmd.extend(["-G", f"{gpu_index}:{gpu_vram_gb}"])

            # Log the calculated resources
            logger.info("===== Raw System Resources =====")
            logger.info("Total CPU cores:            %s", os.cpu_count() or "Unknown")
            logger.info("RAM to onboard (GiB):       %s", resources["ram_gb"])
            logger.info("Disk to onboard (GiB):      %s", resources["disk_gb"])
            if resources["gpus"]:
                for gpu_index, gpu_vram_gb in resources["gpus"]:
                    logger.info("GPU index to onboard:       %s", gpu_index)
                    logger.info("GPU VRAM to onboard (GiB):  %s", gpu_vram_gb)
            else:
                logger.info("GPU onboarding:             skipped (no GPUs detected)")

            logger.info("===== Onboarding DMS =====")
            logger.info("Command: %s", " ".join(cmd))

            # Execute the onboarding command with output capture for better error reporting
            # Use capture_output=True with encoding to ensure output is captured even if binary
            cp = run_dms_command_with_passphrase(
                cmd,
                capture_output=True,  # This captures both stdout and stderr
                text=True,
                encoding='utf-8',
                errors='replace',  # Replace invalid UTF-8 sequences instead of failing
                check=False,
            )

            if cp.returncode == 0:
                return {
                    "status": "success",
                    "message": "Compute resources onboarded successfully",
                    "stdout": cp.stdout or "",
                    "stderr": cp.stderr or "",
                }

            # Build error message with available information
            stdout_str = cp.stdout or ""
            stderr_str = cp.stderr or ""
            
            if not stdout_str and not stderr_str:
                error_msg = f"Command failed with return code {cp.returncode} (no output captured)"
                logger.error("Onboarding failed: %s. Command: %s", error_msg, " ".join(cmd))
            else:
                error_msg = stderr_str.strip() or stdout_str.strip() or f"Command failed with return code {cp.returncode}"
                logger.error("Onboarding failed: %s", error_msg)
                if stdout_str:
                    logger.debug("Onboarding stdout: %s", stdout_str)
                if stderr_str:
                    logger.debug("Onboarding stderr: %s", stderr_str)
            
            return {
                "status": "error",
                "message": error_msg,
                "stdout": stdout_str,
                "stderr": stderr_str,
                "returncode": cp.returncode,
            }
        except Exception as exc:
            logger.exception("Unexpected error during compute onboarding")
            return {"status": "error", "message": str(exc)}

    def offboard_compute(self) -> Dict[str, str]:
        cp = run_dms_command_with_passphrase(
            ["nunet", "-c", "dms", "actor", "cmd", "/dms/node/onboarding/offboard"],
            capture_output=True,
            text=True,
            check=False,
        )
        if cp.returncode == 0:
            return {"status": "success", "message": cp.stdout or ""}
        message = cp.stderr or cp.stdout or f"Command failed with return code {cp.returncode}"
        logger.error("Failed to offboard compute: %s", message)
        return {"status": "error", "message": message}

    def get_resource_allocation(self) -> Dict[str, str]:
        cp = run_dms_command_with_passphrase(
            ["nunet", "-c", "dms", "actor", "cmd", "/dms/node/resources/allocated"],
            capture_output=True,
            text=True,
            check=False,
        )
        if cp.returncode == 0:
            return {"status": "success", "message": cp.stdout or ""}
        message = cp.stderr or cp.stdout or f"Command failed with return code {cp.returncode}"
        logger.error("Failed to fetch resource allocation: %s", message)
        return {"status": "error", "message": message}

    def update_dms(self) -> Dict[str, str]:
        arch = platform.machine().lower()
        logger.info("Detected architecture: %s", arch)
        candidates = self._package_candidates_for_arch(arch)
        if not candidates:
            message = f"Unsupported architecture: {arch}"
            logger.error(message)
            return {"status": "error", "message": message}

        last_error = "Unknown error"
        for idx, (channel, url) in enumerate(candidates):
            logger.info("Trying DMS update channel=%s url=%s", channel, url)
            self._run(["rm", "-f", "dms-package.deb"], capture=True, check=False)
            download = self._run(["wget", "-N", url, "-O", "dms-package.deb"], capture=True, check=False)
            if download.returncode != 0:
                message = download.stderr or download.stdout or "Download failed"
                last_error = f"Download failed ({channel}): {message}"
                logger.warning("Failed to download DMS package from %s: %s", channel, message)
                continue

            install = self._run(
                ["sudo", "apt", "install", "./dms-package.deb", "-y", "--allow-downgrades"],
                capture=True,
                check=False,
            )
            if install.returncode == 0:
                self._run(["rm", "-f", "dms-package.deb"], capture=True, check=False)
                logger.info("DMS updated successfully via channel=%s", channel)
                return {"status": "success", "message": "DMS updated successfully."}

            message = install.stderr or install.stdout or "Installation failed"
            last_error = f"Installation failed ({channel}): {message}"
            logger.error("Failed to install DMS package from channel=%s: %s", channel, message)
            self._run(["rm", "-f", "dms-package.deb"], capture=True, check=False)

        return {"status": "error", "message": last_error}

    @staticmethod
    def _normalize_contract_list_payload(result: DmsCommandResult) -> Dict[str, Any]:
        data = result.get("data")
        if not isinstance(data, dict):
            logger.debug("Unexpected payload for %s: %s", result.get("endpoint"), data)
            return {"contracts": [], "raw": data}
        contracts = data.get("contracts")
        if isinstance(contracts, list):
            return {"contracts": contracts, "raw": data}
        logger.debug("Missing 'contracts' key in %s payload: %s", result.get("endpoint"), data)
        return {"contracts": [], "raw": data}

    @staticmethod
    def _filter_contracts_by_view(contracts: Sequence[Dict[str, Any]], view: str) -> List[Dict[str, Any]]:
        normalized = (view or "all").lower()
        if normalized == "incoming":
            allowed = DMSManager._INCOMING_STATES
        elif normalized == "active":
            allowed = DMSManager._ACTIVE_STATES
        else:
            return list(contracts)
        filtered: List[Dict[str, Any]] = []
        for entry in contracts:
            state = str(entry.get("current_state", "")).upper()
            if state in allowed:
                filtered.append(entry)
        return filtered

    @staticmethod
    def _annotate_contracts(contracts: Sequence[Dict[str, Any]], view: str) -> List[Dict[str, Any]]:
        annotated: List[Dict[str, Any]] = []
        for entry in contracts:
            if not isinstance(entry, dict):
                continue
            enriched = dict(entry)
            enriched.setdefault("list_view", view)
            annotated.append(enriched)
        return annotated

    @staticmethod
    def _merge_contract_sets(*collections: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
        merged: List[Dict[str, Any]] = []
        seen: set[str] = set()
        for collection in collections:
            for entry in collection:
                if not isinstance(entry, dict):
                    continue
                contract_did = entry.get("contract_did")
                if isinstance(contract_did, str):
                    if contract_did in seen:
                        continue
                    seen.add(contract_did)
                merged.append(entry)
        return merged

    def _list_single_view(
        self,
        executor: Callable[..., DmsCommandResult],
        *,
        normalized_view: str,
        timeout: int,
        filter_view: Optional[str],
        error_message: str,
    ) -> Dict[str, Any]:
        result = executor(timeout=timeout)
        if not result.get("success"):
            return self._contract_error(result, error_message)
        payload = self._normalize_contract_list_payload(result)
        contracts = payload.get("contracts", [])
        annotated = self._annotate_contracts(contracts, normalized_view)
        filtered = self._filter_contracts_by_view(annotated, filter_view) if filter_view else list(annotated)
        payload["contracts"] = filtered
        payload["filter"] = normalized_view
        payload["total_count"] = len(contracts)
        payload["filtered_count"] = len(filtered)
        return self._contract_success(result, payload)

    def _list_all_contracts(self, *, timeout: int) -> Dict[str, Any]:
        incoming_result = contract_list_incoming(timeout=timeout)
        if not incoming_result.get("success"):
            return self._contract_error(incoming_result, "Failed to list incoming contracts")
        outgoing_result = contract_list_outgoing(timeout=timeout)

        incoming_payload = self._normalize_contract_list_payload(incoming_result)
        outgoing_warning: Optional[str] = None
        outgoing_payload: Dict[str, Any] = {"contracts": [], "raw": None}
        outgoing_success = bool(outgoing_result.get("success"))
        if outgoing_success:
            outgoing_payload = self._normalize_contract_list_payload(outgoing_result)
        else:
            if outgoing_result.get("error_code") == "contracts_cli_missing":
                outgoing_warning = outgoing_result.get("error") or "Outgoing contracts are unavailable on this nunet CLI."
            else:
                return self._contract_error(outgoing_result, "Failed to list outgoing contracts")

        incoming_contracts = self._annotate_contracts(incoming_payload.get("contracts", []), "incoming")
        outgoing_contracts = (
            self._annotate_contracts(outgoing_payload.get("contracts", []), "outgoing") if outgoing_success else []
        )
        combined_contracts = self._merge_contract_sets(incoming_contracts, outgoing_contracts)
        active_contracts = self._filter_contracts_by_view(incoming_payload.get("contracts", []), "active")

        payload = {
            "contracts": combined_contracts,
            "filter": "all",
            "total_count": len(combined_contracts),
            "filtered_count": len(combined_contracts),
            "raw": {
                "incoming": incoming_payload.get("raw"),
                "outgoing": outgoing_payload.get("raw") if outgoing_success else {"warning": outgoing_warning},
                "active": {"contracts": active_contracts},
            },
        }

        response = self._contract_success(incoming_result, payload)
        response["stdout"] = "\n".join(
            filter(None, [incoming_result.get("stdout"), outgoing_result.get("stdout")])
        ) or None
        response["stderr"] = "\n".join(
            filter(None, [incoming_result.get("stderr"), outgoing_result.get("stderr")])
        ) or None
        if outgoing_warning:
            existing = response.get("message") or incoming_result.get("message")
            response["message"] = " ".join(filter(None, [existing, outgoing_warning]))
        else:
            response["message"] = incoming_result.get("message") or outgoing_result.get("message")
        return response

    def list_contracts(self, view: str = "all", *, timeout: int = 30) -> Dict[str, Any]:
        normalized_view = (view or "all").lower()
        if normalized_view == "incoming":
            return self._list_single_view(
                contract_list_incoming,
                normalized_view="incoming",
                timeout=timeout,
                filter_view="incoming",
                error_message="Failed to list incoming contracts",
            )
        if normalized_view == "outgoing":
            return self._list_single_view(
                contract_list_outgoing,
                normalized_view="outgoing",
                timeout=timeout,
                filter_view=None,
                error_message="Failed to list outgoing contracts",
            )
        if normalized_view == "active":
            return self._list_single_view(
                contract_list_incoming,
                normalized_view="active",
                timeout=timeout,
                filter_view="active",
                error_message="Failed to list signed contracts",
            )
        return self._list_all_contracts(timeout=timeout)

    def list_incoming_contracts(self, *, timeout: int = 30) -> Dict[str, Any]:
        return self.list_contracts("incoming", timeout=timeout)

    def list_outgoing_contracts(self, *, timeout: int = 30) -> Dict[str, Any]:
        return self.list_contracts("outgoing", timeout=timeout)

    def list_signed_contracts(self, *, timeout: int = 30) -> Dict[str, Any]:
        return self.list_contracts("active", timeout=timeout)

    def get_contract_state(
        self,
        contract_did: str,
        *,
        contract_host_did: Optional[str] = None,
        timeout: int = 30,
    ) -> Dict[str, Any]:
        result = contract_state(contract_did, contract_host_did=contract_host_did, timeout=timeout)
        if not result.get("success"):
            return self._contract_error(
                result,
                f"Failed to fetch contract state for {contract_did}",
            )
        payload = {"contract": result.get("data")}
        return self._contract_success(result, payload)

    def create_contract(
        self,
        contract_file: str,
        *,
        extra_args: Optional[Sequence[str]] = None,
        template_id: Optional[str] = None,
        timeout: int = 60,
    ) -> Dict[str, Any]:
        result = contract_create(
            contract_file,
            extra_args=extra_args,
            timeout=timeout,
        )
        if not result.get("success"):
            return self._contract_error(result, "Failed to create contract")
        message = (result.get("stdout") or "").strip() or "Contract create command dispatched"
        payload: Dict[str, Any] = {"message": message, "contract_file": contract_file}
        if template_id:
            payload["template_id"] = template_id
        return self._contract_success(result, payload)

    def approve_contract(
        self,
        contract_did: str,
        *,
        extra_args: Optional[Sequence[str]] = None,
        timeout: int = 30,
    ) -> Dict[str, Any]:
        result = contract_approve_local(
            contract_did,
            extra_args=extra_args,
            timeout=timeout,
        )
        if not result.get("success"):
            return self._contract_error(
                result,
                f"Failed to approve contract {contract_did}",
            )
        message = (result.get("stdout") or "").strip() or "Contract approval command dispatched"
        payload = {"message": message, "contract_did": contract_did}
        return self._contract_success(result, payload)

    def terminate_contract(
        self,
        contract_did: str,
        *,
        contract_host_did: Optional[str] = None,
        extra_args: Optional[Sequence[str]] = None,
        timeout: int = 30,
    ) -> Dict[str, Any]:
        result = contract_terminate(
            contract_did,
            contract_host_did=contract_host_did,
            extra_args=extra_args,
            timeout=timeout,
        )
        if not result.get("success"):
            return self._contract_error(
                result,
                f"Failed to terminate contract {contract_did}",
            )
        message = (result.get("stdout") or "").strip() or "Contract termination command dispatched"
        payload: Dict[str, Any] = {"message": message, "contract_did": contract_did}
        if contract_host_did:
            payload["contract_host_did"] = contract_host_did
        return self._contract_success(result, payload)

    @staticmethod
    def _extract_error(stdout: str, stderr: str) -> Optional[str]:
        for stream in (stderr, stdout):
            if stream:
                lowered = stream.lower()
                if "error" in lowered or "failed" in lowered or "failure" in lowered:
                    return stream.strip()
        if not stdout:
            return None
        try:
            data = json.loads(stdout)
        except json.JSONDecodeError:
            return None
        if isinstance(data, dict):
            status = data.get("status") or data.get("Status")
            if isinstance(status, str) and status.lower() in {"error", "failed", "failure"}:
                message = data.get("message") or data.get("Message") or data.get("error") or data.get("Error")
                if isinstance(message, str) and message.strip():
                    return message.strip()
                return stdout.strip()
            for key in ("error", "Error", "message", "Message"):
                value = data.get(key)
                if isinstance(value, str) and value.strip() and "error" in value.lower():
                    return value.strip()
        return None

    @staticmethod
    def _normalize_blockchain(blockchain: Optional[str]) -> str:
        if not blockchain:
            return DEFAULT_BLOCKCHAIN
        normalized = blockchain.strip().upper()
        if normalized in SUPPORTED_BLOCKCHAINS:
            return normalized
        raise ValueError(
            f"Unsupported blockchain '{blockchain}'. Expected one of: {', '.join(sorted(SUPPORTED_BLOCKCHAINS))}"
        )

    @staticmethod
    def _parse_json_output(stdout: str) -> Optional[Dict[str, Any]]:
        if not stdout:
            return None
        try:
            payload = json.loads(stdout)
        except json.JSONDecodeError:
            return None
        if isinstance(payload, dict):
            return payload
        return None

    @staticmethod
    def _is_terminal_quote_error(message: Optional[str]) -> bool:
        if not isinstance(message, str) or not message.strip():
            return False
        lowered = message.lower()
        return any(
            marker in lowered
            for marker in (
                "quote already used",
                "quote not found",
                "quote expired",
            )
        )

    @staticmethod
    def _is_idempotent_quote_cancel_error(message: Optional[str]) -> bool:
        if not isinstance(message, str) or not message.strip():
            return False
        lowered = message.lower()
        return "quote already used" in lowered or "quote not found" in lowered

    def confirm_transaction(
        self,
        unique_id: str,
        tx_hash: str,
        blockchain: Optional[str] = None,
        quote_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        try:
            normalized_blockchain = self._normalize_blockchain(blockchain)
        except ValueError as exc:
            logger.error("Invalid blockchain for confirm_transaction: %s", exc)
            return {"status": "error", "message": str(exc)}

        base_argv = [
            "nunet", "actor", "cmd", "--context", "dms",
            "/dms/tokenomics/contract/transactions/confirm",
            "--unique-id", unique_id,
            "--tx-hash", tx_hash,
        ]
        argv = list(base_argv)
        if quote_id:
            argv.extend(["--quote-id", quote_id])
        argv.extend(["--blockchain", normalized_blockchain])
        supports_blockchain_flag = True
        supports_quote_flag = bool(quote_id)
        last_error: Optional[str] = None
        max_attempts = 6  # allow longer for Cardano block times
        retry_delay_sec = 10
        for attempt in range(1, max_attempts + 1):
            cp = run_dms_command_with_passphrase(argv, capture_output=True, text=True, check=False)
            stdout = (cp.stdout or "").strip()
            stderr = (cp.stderr or "").strip()
            error_text_lower = f"{stderr}\n{stdout}".lower()
            command_error: Optional[str] = None

            # If the CLI returns JSON with {"error": ""}, treat it as success even if rc != 0.
            try:
                parsed = json.loads(stdout) if stdout else {}
            except Exception:
                parsed = {}
            if isinstance(parsed, dict) and parsed.get("error") == "":
                return {"status": "success", "stdout": stdout, "stderr": stderr}

            if cp.returncode == 0:
                error_message = self._extract_error(stdout, stderr)
                if not error_message:
                    return {"status": "success", "stdout": stdout, "stderr": stderr}
                command_error = error_message
                logger.debug("Confirm transaction returned error payload (attempt %s): %s", attempt, error_message)
            else:
                if supports_quote_flag and "unknown flag: --quote-id" in error_text_lower:
                    logger.warning("confirm_transaction: CLI does not support --quote-id flag, retrying without it")
                    supports_quote_flag = False
                    argv = list(base_argv)
                    argv.extend(["--blockchain", normalized_blockchain])
                    if attempt < max_attempts:
                        continue
                if supports_blockchain_flag and "unknown flag: --blockchain" in error_text_lower:
                    logger.warning("confirm_transaction: CLI does not support --blockchain flag, retrying without it")
                    supports_blockchain_flag = False
                    argv = list(base_argv)
                    if quote_id and supports_quote_flag:
                        argv.extend(["--quote-id", quote_id])
                    if attempt < max_attempts:
                        continue
                command_error = stderr or stdout or f"Command failed with return code {cp.returncode}"
                logger.debug("Confirm transaction failed (attempt %s): %s", attempt, command_error)

            last_error = command_error
            if self._is_terminal_quote_error(command_error):
                # If the quote has been consumed before this confirm returns, retry once
                # without --quote-id so we can still attach tx_hash idempotently.
                if quote_id and supports_quote_flag:
                    logger.warning(
                        "confirm_transaction: quote terminal error encountered (%s); retrying without --quote-id",
                        command_error,
                    )
                    supports_quote_flag = False
                    argv = list(base_argv)
                    if supports_blockchain_flag:
                        argv.extend(["--blockchain", normalized_blockchain])
                    if attempt < max_attempts:
                        continue
                logger.info("confirm_transaction: stopping retries due to terminal quote error: %s", command_error)
                break

            if attempt < max_attempts:
                # For transient validation responses (e.g., "not verified" while waiting for block),
                # back off before retrying.
                time.sleep(retry_delay_sec)
        return {"status": "error", "message": last_error or "Transaction confirmation failed"}

    def get_payment_quote(self, unique_id: str) -> Dict[str, Any]:
        cmd = [
            "nunet", "actor", "cmd", "--context", "dms",
            "/dms/tokenomics/contract/payment/quote/get",
            "--unique-id", unique_id,
        ]
        cp = run_dms_command_with_passphrase(
            cmd,
            capture_output=True,
            text=True,
            check=False,
        )
        stdout = (cp.stdout or "").strip()
        stderr = (cp.stderr or "").strip()
        parsed = self._parse_json_output(stdout)

        if cp.returncode != 0:
            message = (
                (parsed or {}).get("error")
                or (parsed or {}).get("message")
                or stderr
                or stdout
                or f"Command failed with return code {cp.returncode}"
            )
            logger.error("Failed to get payment quote for %s: %s", unique_id, message)
            return {"status": "error", "message": message}
        if not parsed:
            logger.error("Invalid JSON from payment quote get command: %s", stdout)
            return {"status": "error", "message": "Invalid JSON from DMS payment quote get"}

        error_message = parsed.get("error")
        if isinstance(error_message, str) and error_message.strip():
            logger.warning("Payment quote get returned error for %s: %s", unique_id, error_message.strip())
            return {"status": "error", "message": error_message.strip()}

        payload = {"status": "success"}
        payload.update(parsed)
        return payload

    def validate_payment_quote(self, quote_id: str) -> Dict[str, Any]:
        cmd = [
            "nunet", "actor", "cmd", "--context", "dms",
            "/dms/tokenomics/contract/payment/quote/validate",
            "--quote-id", quote_id,
        ]
        cp = run_dms_command_with_passphrase(
            cmd,
            capture_output=True,
            text=True,
            check=False,
        )
        stdout = (cp.stdout or "").strip()
        stderr = (cp.stderr or "").strip()
        parsed = self._parse_json_output(stdout)

        if cp.returncode != 0:
            message = (
                (parsed or {}).get("error")
                or (parsed or {}).get("message")
                or stderr
                or stdout
                or f"Command failed with return code {cp.returncode}"
            )
            logger.error("Failed to validate payment quote %s: %s", quote_id, message)
            return {"status": "error", "message": message}
        if not parsed:
            logger.error("Invalid JSON from payment quote validate command: %s", stdout)
            return {"status": "error", "message": "Invalid JSON from DMS payment quote validate"}

        payload = {"status": "success"}
        payload.update(parsed)
        return payload

    def cancel_payment_quote(self, quote_id: str) -> Dict[str, Any]:
        cmd = [
            "nunet", "actor", "cmd", "--context", "dms",
            "/dms/tokenomics/contract/payment/quote/cancel",
            "--quote-id", quote_id,
        ]
        cp = run_dms_command_with_passphrase(
            cmd,
            capture_output=True,
            text=True,
            check=False,
        )
        stdout = (cp.stdout or "").strip()
        stderr = (cp.stderr or "").strip()
        parsed = self._parse_json_output(stdout)

        if cp.returncode != 0:
            message = (
                (parsed or {}).get("error")
                or (parsed or {}).get("message")
                or stderr
                or stdout
                or f"Command failed with return code {cp.returncode}"
            )
            if self._is_idempotent_quote_cancel_error(message):
                logger.info("Payment quote cancel is idempotent for %s: %s", quote_id, message)
                return {"status": "success", "message": message}
            logger.error("Failed to cancel payment quote %s: %s", quote_id, message)
            return {"status": "error", "message": message}
        if parsed and isinstance(parsed.get("error"), str) and parsed.get("error", "").strip():
            message = parsed["error"].strip()
            if self._is_idempotent_quote_cancel_error(message):
                logger.info("Payment quote cancel is idempotent for %s: %s", quote_id, message)
                payload = {"status": "success"}
                payload.update(parsed)
                return payload
            logger.warning("Payment quote cancel returned error for %s: %s", quote_id, message)
            return {"status": "error", "message": message}

        payload = {"status": "success"}
        if parsed:
            payload.update(parsed)
        return payload

    def list_transactions(self, blockchain: Optional[str] = None) -> Dict[str, Any]:
        base_cmd = [
            "nunet", "actor", "cmd", "--context", "dms",
            "/dms/tokenomics/contract/transactions/list",
        ]
        cp = run_dms_command_with_passphrase(
            base_cmd,
            capture_output=True,
            text=True,
            check=False,
        )
        stdout = cp.stdout or ""
        stderr = cp.stderr or ""
        if cp.returncode != 0:
            message = stderr or stdout or f"Command failed with return code {cp.returncode}"
            logger.error("Failed to list transactions: %s", message)
            return {"status": "error", "message": message}
        try:
            data = json.loads(stdout or "{}")
        except json.JSONDecodeError:
            logger.error("Invalid JSON from transactions list command")
            return {"status": "error", "message": "Invalid JSON from DMS /transactions/list"}
        transactions = data.get("transactions", [])
        return {"status": "success", "transactions": transactions}

    def get_structured_logs(
        self,
        alloc_dir: Optional[Path] = None,
        *,
        lines: int = 200,
        refresh_alloc_logs: bool = True,
        include_dms_logs: bool = True,
    ) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "status": "success",
            "message": "Structured logs fetched",
            "allocation": None,
            "dms_logs": None,
        }

        result["dms_logs"] = _journalctl_dms(lines) if include_dms_logs else None

        if alloc_dir:
            base = DMS_DEPLOYMENTS_LOGS
            alloc_path = Path(alloc_dir)
            base, alloc_path = _rebase_allocation_path(base, alloc_path)
            if not _safe_under(base, alloc_path):
                message = f"alloc_dir must live under {base}"
                logger.error(message)
                return {
                    "status": "error",
                    "message": message,
                    "dms_logs": result["dms_logs"],
                    "allocation": None,
                }

            try:
                # Request fresh stdout/stderr logs via the DMS CLI before reading files from disk.
                if refresh_alloc_logs:
                    parts = _extract_deployment_allocation(base, alloc_path)
                    if parts:
                        dep_id, allocation_name = parts
                        ok, req_message = _request_allocation_logs(dep_id, allocation_name)
                        if not ok:
                            logger.warning(
                                "Failed to request logs for deployment %s allocation %s: %s",
                                dep_id,
                                allocation_name,
                                req_message or "no message",
                            )
                    else:
                        logger.debug(
                            "Unable to determine deployment/allocation from path: %s",
                            alloc_path,
                        )
            except Exception as exc:  # defensive: log request failures shouldn't abort log collection
                logger.warning("Error requesting allocation logs: %s", exc)

            stdout_path = alloc_path / "stdout.logs"
            stderr_path = alloc_path / "stderr.logs"
            allocation = {
                "dir": str(alloc_path),
                "stdout": _make_filelog(stdout_path, lines),
                "stderr": _make_filelog(stderr_path, lines),
            }
            result["allocation"] = allocation
            if not allocation["stdout"]["exists"] and not allocation["stderr"]["exists"]:
                result["message"] = "Structured logs fetched (allocation files not found)"

        return result

    def get_filtered_dms_logs(
        self,
        deployment_id: str,
        *,
        query: Optional[str] = None,
        max_lines: int = 400,
        last_run: bool = True,
        view: str = "compact",
    ) -> Dict[str, Any]:
        return _filtered_dms_logs_from_file(
            deployment_id,
            query=query,
            max_lines=max_lines,
            last_run=last_run,
            view=view,
        )

    def get_filtered_dms_logs_general(
        self,
        *,
        query: Optional[str] = None,
        max_lines: int = 400,
        last_run: bool = True,
        view: str = "compact",
    ) -> Dict[str, Any]:
        return _filtered_dms_logs_from_file(
            None,
            query=query,
            max_lines=max_lines,
            last_run=last_run,
            view=view,
        )


def _to_iso(ts: float) -> Optional[str]:
    try:
        return datetime.utcfromtimestamp(ts).isoformat() + "Z"
    except Exception:
        return None


def _run_capture(
    argv: List[str],
    env: Optional[Dict[str, str]] = None,
    cwd: Optional[Path | str] = None,
    timeout: int = 30,
) -> subprocess.CompletedProcess:
    logger.debug("Capturing command output: %s", " ".join(argv))
    return subprocess.run(
        argv,
        text=True,
        capture_output=True,
        env=env,
        cwd=str(cwd) if isinstance(cwd, Path) else cwd,
        timeout=timeout,
        check=False,
    )


def _safe_under(base: Path, child: Path) -> bool:
    try:
        return str(child.resolve()).startswith(str(base.resolve()))
    except Exception:
        return False


def _rebase_allocation_path(base: Path, alloc_path: Path) -> Tuple[Path, Path]:
    """
    If alloc_dir points to an old location, remap to a known deployments base that exists.
    Keeps path_constants minimal while still resolving the live DMS path.
    """
    candidates: List[Path] = []
    seen: set[str] = set()
    for candidate in (base, DMS_DEPLOYMENTS_DIR, Path("/home/nunet/nunet/deployments")):
        try:
            p = Path(candidate)
        except Exception:
            continue
        key = str(p)
        if key in seen:
            continue
        seen.add(key)
        candidates.append(p)

    alloc_exists = False
    try:
        alloc_exists = alloc_path.exists()
    except Exception:
        pass

    for candidate in candidates:
        if _safe_under(candidate, alloc_path) and alloc_exists:
            return candidate, alloc_path

    try:
        rel = alloc_path.relative_to(base)
    except Exception:
        rel = None

    if rel is not None:
        for candidate in candidates:
            mapped = candidate / rel
            try:
                if mapped.exists():
                    return candidate, mapped
            except Exception:
                continue

    parts = alloc_path.parts[-2:]
    if len(parts) == 2:
        for candidate in candidates:
            mapped = candidate / parts[0] / parts[1]
            try:
                if mapped.exists():
                    return candidate, mapped
            except Exception:
                continue

    return base, alloc_path


def _stat_file_with_sudo(path: Path) -> Tuple[Optional[int], Optional[str], Optional[str]]:
    cp = _run_capture(["sudo", "-n", "stat", "-c", "%s,%Y", str(path)])
    if cp.returncode == 0:
        try:
            size_s, mtime_s = (cp.stdout.strip() or "").split(",", 1)
            size = int(size_s)
            mtime_iso = _to_iso(float(mtime_s))
            return size, mtime_iso, None
        except Exception as exc:
            return None, None, f"stat parse error: {exc}"
    return None, None, (cp.stderr or cp.stdout or "").strip() or "stat failed"


def _tail_file_with_sudo(path: Path, lines: int) -> Tuple[str, bool, Optional[str]]:
    cp = _run_capture(["sudo", "-n", "tail", "-n", str(lines), str(path)])
    if cp.returncode == 0:
        return cp.stdout, True, None
    err = (cp.stderr or cp.stdout or "").strip() or f"tail failed rc={cp.returncode}"
    return "", False, err


def _resolve_log_path(path: Path) -> Tuple[Path, bool]:
    candidates = [path]
    suffix = path.suffix.lower()
    try:
        if suffix == ".logs":
            candidates.append(path.with_suffix(".log"))
        elif suffix == ".log":
            candidates.append(path.with_suffix(".logs"))
        else:
            candidates.append(path.with_suffix(".logs"))
            candidates.append(path.with_suffix(".log"))
    except ValueError:
        pass

    seen: set[str] = set()
    unique_candidates: List[Path] = []
    for candidate in candidates:
        key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        unique_candidates.append(candidate)

    for candidate in unique_candidates:
        try:
            if candidate.exists():
                return candidate, True
        except Exception:
            continue
    return path, False


def _make_filelog(path: Path, lines: int) -> Dict[str, Any]:
    resolved_path, exists = _resolve_log_path(path)
    size, mtime_iso, stat_err = (None, None, None)
    content, readable, read_err = ("", False, None)

    if exists:
        size, mtime_iso, stat_err = _stat_file_with_sudo(resolved_path)
        content, readable, read_err = _tail_file_with_sudo(resolved_path, lines)

    error = None
    if not exists:
        error = "file not found"
    elif not readable:
        error = read_err or stat_err
    elif stat_err:
        error = stat_err

    return {
        "path": str(resolved_path),
        "exists": exists,
        "readable": readable,
        "size_bytes": size,
        "mtime_iso": mtime_iso,
        "tail_lines": lines,
        "content": content if readable else None,
        "error": error,
    }


def _journalctl_dms(lines: int) -> Dict[str, Any]:
    cp = _run_capture(
        [
            "sudo", "-n", "journalctl", "-u", "nunetdms",
            "-n", str(lines), "--no-pager", "--output=short-iso",
        ],
        timeout=60,
    )
    return {
        "source": "journalctl",
        "lines": lines,
        "stdout": cp.stdout or "",
        "stderr": cp.stderr or "",
        "returncode": cp.returncode,
    }


def _filtered_dms_logs_from_file(
    deployment_id: Optional[str],
    *,
    query: Optional[str] = None,
    max_lines: int = 400,
    last_run: bool = True,
    view: str = "compact",
) -> Dict[str, Any]:
    deployment_id = (deployment_id or "").strip()

    if not shutil.which("jq"):
        return {
            "source": "file",
            "stdout": "",
            "stderr": "jq not available",
            "returncode": 127,
        }

    log_path = _resolve_dms_log_path()
    if not log_path:
        return {
            "source": "file",
            "stdout": "",
            "stderr": "DMS log file not found",
            "returncode": 1,
        }

    deployment_query = None
    if deployment_id:
        deployment_value = json.dumps(deployment_id)
        deployment_query = (
            f"(.orchestratorID == {deployment_value}) or "
            f"((.allocationID // \"\") | startswith({deployment_value}))"
        )

    final_query = None
    if deployment_query and query:
        final_query = f"({deployment_query}) and ({query})"
    elif deployment_query:
        final_query = deployment_query
    elif query:
        final_query = query

    tail_cmd = ["tail", "-n", str(max_lines), str(log_path)] if max_lines > 0 else ["cat", str(log_path)]
    tail_cp = _run_capture(tail_cmd, timeout=30)
    if tail_cp.returncode != 0:
        return {
            "source": "file",
            "lines": max_lines if max_lines > 0 else None,
            "stdout": "",
            "stderr": tail_cp.stderr or f"Failed to read {log_path}",
            "returncode": tail_cp.returncode,
        }

    raw_lines = tail_cp.stdout or ""
    if not raw_lines.strip():
        return {
            "source": "file",
            "lines": max_lines if max_lines > 0 else None,
            "stdout": "",
            "stderr": "",
            "returncode": 0,
        }

    base_expr = "fromjson? | select(. != null)"
    jq_expr = f"{base_expr} | select({final_query})" if final_query else base_expr
    jq_cp = subprocess.run(
        ["jq", "-R", "-c", jq_expr],
        input=raw_lines,
        text=True,
        capture_output=True,
        check=False,
    )
    if jq_cp.returncode != 0:
        return {
            "source": "file",
            "lines": max_lines if max_lines > 0 else None,
            "stdout": "",
            "stderr": jq_cp.stderr or "jq filtering failed",
            "returncode": jq_cp.returncode,
        }

    view = _normalize_dms_view(view)
    formatted = []
    for line in (jq_cp.stdout or "").splitlines():
        line = line.strip()
        if not line:
            continue
        if view == "raw":
            formatted.append(line)
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            formatted.append(line)
            continue
        if view == "expanded":
            formatted.append(_format_dms_log_entry_expanded(entry))
        elif view == "folded":
            formatted.append(_format_dms_log_entry_folded(entry))
        elif view == "map":
            formatted.append(_format_dms_log_entry_map(entry))
        else:
            formatted.append(_format_dms_log_entry(entry))

    return {
        "source": "file",
        "lines": max_lines if max_lines > 0 else None,
        "stdout": ("\n\n" if view == "expanded" else "\n").join(formatted),
        "stderr": "",
        "returncode": 0,
    }


def _resolve_dms_log_path() -> Optional[Path]:
    candidates: list[str] = []
    if NUNET_CONFIG_PATH.exists():
        try:
            cfg = json.loads(NUNET_CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception:
            cfg = {}
        if isinstance(cfg, dict):
            observability = cfg.get("observability") or {}
            logging_cfg = observability.get("logging") or {}
            candidates.extend(
                [
                    logging_cfg.get("file"),
                    observability.get("log_file"),
                    cfg.get("log_file"),
                ]
            )
            if "logging" in cfg and isinstance(cfg.get("logging"), dict):
                candidates.append(cfg["logging"].get("file"))

    candidates.append(str(DMS_LOG_JSONL_PATH))
    candidates.append(str(DMS_LOG_PATH))
    unreadable_candidate: Optional[Path] = None
    for candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate)
        try:
            if path.exists():
                if os.access(path, os.R_OK):
                    return path
                if unreadable_candidate is None:
                    unreadable_candidate = path
        except PermissionError as exc:
            logger.warning("Permission denied reading DMS log path %s: %s", path, exc)
            if unreadable_candidate is None:
                unreadable_candidate = path
        except OSError as exc:
            logger.debug("Unable to stat DMS log path %s: %s", path, exc)
    return unreadable_candidate


def _format_dms_log_entry(entry: Dict[str, Any]) -> str:
    timestamp = entry.get("timestamp") or entry.get("time")
    level = entry.get("level")
    msg = entry.get("msg") or entry.get("message")

    parts = [p for p in (timestamp, level, msg) if p]
    extras = []
    for key in ("orchestratorID", "deploymentID", "allocationID", "behavior", "did"):
        value = entry.get(key)
        if value:
            extras.append(f"{key}={value}")
    if entry.get("error"):
        extras.append(f"error={entry.get('error')}")

    line = " ".join(parts).strip()
    if extras:
        line = f"{line} | {' '.join(extras)}".strip()
    return line or json.dumps(entry, separators=(",", ":"))


def _format_dms_log_entry_folded(entry: Dict[str, Any]) -> str:
    timestamp = entry.get("timestamp") or entry.get("time")
    level = entry.get("level")
    msg = entry.get("msg") or entry.get("message")
    parts = [p for p in (timestamp, level, msg) if p]
    return " ".join(parts).strip() or json.dumps(entry, separators=(",", ":"))


def _format_dms_log_entry_map(entry: Dict[str, Any]) -> str:
    msg = entry.get("msg") or entry.get("message")
    if msg:
        return str(msg)
    return _format_dms_log_entry_folded(entry)


def _format_dms_log_entry_expanded(entry: Dict[str, Any]) -> str:
    try:
        return json.dumps(entry, indent=2, sort_keys=True, ensure_ascii=True)
    except Exception:
        return json.dumps(entry, separators=(",", ":"), ensure_ascii=True)


def _normalize_dms_view(view: Optional[str]) -> str:
    allowed = {"compact", "folded", "expanded", "map", "raw"}
    if not view or view not in allowed:
        return "compact"
    return view


def _extract_deployment_allocation(base: Path, alloc_path: Path) -> Optional[Tuple[str, str]]:
    try:
        rel = alloc_path.resolve(strict=False).relative_to(base.resolve(strict=False))
    except Exception:
        return None

    parts = rel.parts
    if len(parts) >= 2:
        return parts[0], parts[1]
    return None


def _request_allocation_logs(deployment_id: str, allocation_name: str) -> Tuple[bool, Optional[str]]:
    cmd = [
        "nunet",
        "-c",
        "dms",
        "actor",
        "cmd",
        "/dms/node/deployment/logs",
        "--id",
        deployment_id,
        "--allocation",
        allocation_name,
    ]
    try:
        cp = run_dms_command_with_passphrase(
            cmd,
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )
    except FileNotFoundError:
        return False, "nunet CLI not available"
    except subprocess.TimeoutExpired as exc:
        return False, f"log request timed out: {exc}"
    except Exception as exc:
        return False, str(exc)

    message = (cp.stdout or cp.stderr or "").strip() or None

    if cp.returncode != 0:
        return False, message

    logger.debug(
        "Log request for deployment %s allocation %s succeeded: %s",
        deployment_id,
        allocation_name,
        message or "no message",
    )
    return True, message
