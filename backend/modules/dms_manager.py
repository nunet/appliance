"""
Device Management Service (DMS) management helpers.
"""

from __future__ import annotations

import json
import platform
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .dms_utils import (
    run_dms_command_with_passphrase,
    categorize_listen_addresses,
)
from .logging_config import get_logger

logger = get_logger(__name__)

NUNET_SERVICE = "nunetdms"
ONBOARD_SCRIPT_NAME = "onboard-max.sh"

DEFAULT_MENU_DIR = Path.home() / "menu"
DEFAULT_SCRIPTS_DIR = DEFAULT_MENU_DIR / "scripts"

POLL_ATTEMPTS = 30
POLL_DELAY_SEC = 1.0


class DMSManager:
    """Helpers for interacting with the DMS via the nunet CLI and systemd."""

    def __init__(self, menu_dir: Optional[Path] = None, scripts_dir: Optional[Path] = None) -> None:
        self.menu_dir = menu_dir or DEFAULT_MENU_DIR
        candidate_scripts_dir = scripts_dir or (self.menu_dir / "scripts")

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
    def _package_url_for_arch(arch: str) -> Optional[str]:
        arch_lower = arch.lower()
        if "arm" in arch_lower or "aarch" in arch_lower:
            return "https://d.nunet.io/nunet-dms-arm64-latest.deb"
        if "x86_64" in arch_lower or "amd64" in arch_lower or "amd" in arch_lower:
            return "https://d.nunet.io/nunet-dms-amd64-latest.deb"
        return None

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

    def onboard_compute(self) -> Dict[str, str]:
        script_path = self.scripts_dir / ONBOARD_SCRIPT_NAME
        if not script_path.exists():
            message = f"Script not found at {script_path}"
            logger.error(message)
            return {"status": "error", "message": message}
        try:
            run_dms_command_with_passphrase([str(script_path)], check=True)
            return {"status": "success", "message": "Compute resources onboarded successfully"}
        except subprocess.CalledProcessError as exc:
            logger.error("Error during compute onboarding: %s", exc)
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
        url = self._package_url_for_arch(arch)
        if not url:
            message = f"Unsupported architecture: {arch}"
            logger.error(message)
            return {"status": "error", "message": message}

        download = self._run(["wget", "-N", url, "-O", "dms-latest.deb"], capture=True, check=False)
        if download.returncode != 0:
            message = download.stderr or download.stdout or "Download failed"
            logger.error("Failed to download DMS package: %s", message)
            return {"status": "error", "message": f"Download failed: {message}"}

        install = self._run(
            ["sudo", "apt", "install", "./dms-latest.deb", "-y", "--allow-downgrades"],
            capture=True,
            check=False,
        )
        if install.returncode == 0:
            self._run(["rm", "-f", "dms-latest.deb"], capture=True, check=False)
            logger.info("DMS updated successfully")
            return {"status": "success", "message": "DMS updated successfully."}

        message = install.stderr or install.stdout or "Installation failed"
        logger.error("Failed to install DMS package: %s", message)
        return {"status": "error", "message": f"Installation failed: {message}"}

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

    def confirm_transaction(self, unique_id: str, tx_hash: str) -> Dict[str, Any]:
        argv = [
            "nunet", "actor", "cmd", "--context", "dms",
            "/dms/tokenomics/contract/transactions/confirm",
            "--unique-id", unique_id,
            "--tx-hash", tx_hash,
        ]
        last_error: Optional[str] = None
        for attempt in range(1, 4):
            cp = run_dms_command_with_passphrase(argv, capture_output=True, text=True, check=False)
            stdout = (cp.stdout or "").strip()
            stderr = (cp.stderr or "").strip()
            if cp.returncode == 0:
                error_message = self._extract_error(stdout, stderr)
                if not error_message:
                    return {"status": "success", "stdout": stdout, "stderr": stderr}
                last_error = error_message
                logger.debug("Confirm transaction returned error payload (attempt %s): %s", attempt, error_message)
            else:
                last_error = stderr or stdout or f"Command failed with return code {cp.returncode}"
                logger.debug("Confirm transaction failed (attempt %s): %s", attempt, last_error)
            if attempt < 3:
                time.sleep(2)
        return {"status": "error", "message": last_error or "Transaction confirmation failed"}

    def list_transactions(self) -> Dict[str, Any]:
        cp = run_dms_command_with_passphrase(
            [
                "nunet", "actor", "cmd", "--context", "dms",
                "/dms/tokenomics/contract/transactions/list",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if cp.returncode != 0:
            message = cp.stderr or cp.stdout or f"Command failed with return code {cp.returncode}"
            logger.error("Failed to list transactions: %s", message)
            return {"status": "error", "message": message}
        try:
            data = json.loads(cp.stdout or "{}")
        except json.JSONDecodeError:
            logger.error("Invalid JSON from transactions list command")
            return {"status": "error", "message": "Invalid JSON from DMS /transactions/list"}
        transactions = data.get("transactions", [])
        return {"status": "success", "transactions": transactions}

    def get_structured_logs(self, alloc_dir: Optional[Path] = None, *, lines: int = 200) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "status": "success",
            "message": "Structured logs fetched",
            "allocation": None,
            "dms_logs": None,
        }

        result["dms_logs"] = _journalctl_dms(lines)

        if alloc_dir:
            base = Path("/home/nunet/nunet/deployments")
            alloc_path = Path(alloc_dir)
            if not _safe_under(base, alloc_path):
                message = f"alloc_dir must live under {base}"
                logger.error(message)
                return {
                    "status": "error",
                    "message": message,
                    "dms_logs": result["dms_logs"],
                    "allocation": None,
                }

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


