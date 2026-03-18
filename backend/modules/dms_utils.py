"""
Utilities for interacting with the Device Management Service (DMS).
"""

import json
import logging
import os
import re
import shlex
import subprocess
import threading
from pathlib import Path
from copy import deepcopy
from time import monotonic
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple, TypedDict

from .path_constants import DMS_DEFAULT_CONTEXT

logger = logging.getLogger(__name__)

_CACHE_TTL_DEFAULT = 30.0

_DMS_STATUS_CACHE: Dict[str, Any] = {"data": None, "timestamp": 0.0}
_DMS_STATUS_LOCK = threading.Lock()

_DMS_RESOURCES_CACHE: Dict[str, Any] = {"data": None, "timestamp": 0.0}
_DMS_RESOURCES_LOCK = threading.Lock()

_DMS_PEERS_CACHE: Dict[str, Any] = {"data": None, "timestamp": 0.0}
_DMS_PEERS_LOCK = threading.Lock()

_ANSI_RE = re.compile(r"\u001b\[[0-9;]*m")
_PRIVATE_IPV4 = re.compile(r"/ip4/(127\.|10\.|192\.168\.|172\.(1[6-9]|2\d|3[0-1])\.)")
_LOG_OUTPUT_MAX = 4000


class DmsCommandResult(TypedDict, total=False):
    """Standard shape for results returned by DMS CLI helpers."""

    success: bool
    endpoint: str
    argv: List[str]
    returncode: int
    stdout: str
    stderr: str
    data: Any
    error: str
    error_code: str

def _read_cache(cache: Dict[str, Any], lock: threading.Lock, ttl: float) -> Any:
    now = monotonic()
    with lock:
        data = cache.get("data")
        ts = cache.get("timestamp", 0.0)
        if data is not None and now - ts < ttl:
            return deepcopy(data)
    return None

def _write_cache(cache: Dict[str, Any], lock: threading.Lock, value: Any) -> None:
    with lock:
        cache["data"] = deepcopy(value)
        cache["timestamp"] = monotonic()

def _clear_cache(cache: Dict[str, Any], lock: threading.Lock) -> None:
    with lock:
        cache["data"] = None
        cache["timestamp"] = 0.0

def invalidate_dms_status_cache() -> None:
    _clear_cache(_DMS_STATUS_CACHE, _DMS_STATUS_LOCK)

def invalidate_dms_resource_cache() -> None:
    _clear_cache(_DMS_RESOURCES_CACHE, _DMS_RESOURCES_LOCK)

def invalidate_dms_peer_cache() -> None:
    _clear_cache(_DMS_PEERS_CACHE, _DMS_PEERS_LOCK)

def invalidate_all_dms_caches() -> None:
    invalidate_dms_status_cache()
    invalidate_dms_resource_cache()
    invalidate_dms_peer_cache()

def _get_keyctl_passphrase(key_name: str = "dms_passphrase") -> Optional[str]:
    try:
        key_id_cp = subprocess.run(
            ["keyctl", "request", "user", key_name],
            capture_output=True,
            text=True,
            check=True,
        )
    except FileNotFoundError:
        logger.warning("keyctl is not available; cannot load %s", key_name)
        return None
    except subprocess.CalledProcessError as exc:
        logger.debug("keyctl request for %s failed: %s", key_name, exc.stderr or exc)
        return None

    key_id = key_id_cp.stdout.strip()
    if not key_id:
        logger.debug("keyctl returned no id for key %s", key_name)
        return None

    try:
        pass_cp = subprocess.run(
            ["keyctl", "pipe", key_id],
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        logger.debug("keyctl pipe for %s failed: %s", key_name, exc.stderr or exc)
        return None

    passphrase = pass_cp.stdout.strip()
    if passphrase:
        return passphrase

    logger.debug("keyctl pipe returned empty passphrase for %s", key_name)
    return None

def _merge_env(user_env: Optional[Dict[str, str]]) -> Dict[str, str]:
    env = os.environ.copy()
    if user_env:
        env.update(user_env)
    # Always prefer keyctl, fall back to ~/.secrets/dms_passphrase if present; do not require env
    passphrase = _get_keyctl_passphrase()
    if not passphrase:
        try:
            secret_path = Path.home() / ".secrets" / "dms_passphrase"
            if secret_path.exists():
                passphrase = secret_path.read_text(encoding="utf-8").strip()
        except Exception as exc:
            logger.debug("Unable to read dms_passphrase file: %s", exc)
    if passphrase:
        env["DMS_PASSPHRASE"] = passphrase
    return env

def _format_cmd_for_log(cmd: Sequence[str]) -> str:
    return " ".join(shlex.quote(str(part)) for part in cmd)


def _log_command_result(
    cmd: Sequence[str],
    cp: subprocess.CompletedProcess,
    *,
    level: int,
) -> None:
    stdout = "<not captured>"
    stderr = "<not captured>"
    if isinstance(cp.stdout, str):
        stdout = _log_snippet(cp.stdout.strip() or "<empty>")
    elif cp.stdout is not None:
        stdout = "<binary>"

    if isinstance(cp.stderr, str):
        stderr = _log_snippet(cp.stderr.strip() or "<empty>")
    elif cp.stderr is not None:
        stderr = "<binary>"

    logger.log(
        level,
        "DMS command finished rc=%s cmd=%s stdout=%s stderr=%s",
        cp.returncode,
        _format_cmd_for_log(cmd),
        stdout,
        stderr,
    )


def run_dms_command_with_passphrase(cmd: List[str], **kwargs) -> subprocess.CompletedProcess:
    """Run a command ensuring the DMS passphrase is available in the environment."""
    env = _merge_env(kwargs.pop("env", None))
    kwargs.setdefault("text", True)
    check_requested = kwargs.pop("check", False)
    cmd_display = _format_cmd_for_log(cmd)
    logger.info("Executing DMS command: %s", cmd_display)

    try:
        cp = subprocess.run(cmd, env=env, check=False, **kwargs)
    except Exception:
        logger.exception("Failed to execute DMS command: %s", cmd_display)
        raise

    log_level = logging.INFO if cp.returncode == 0 else logging.WARNING
    _log_command_result(cmd, cp, level=log_level)

    if check_requested and cp.returncode != 0:
        raise subprocess.CalledProcessError(
            cp.returncode,
            cmd,
            output=cp.stdout,
            stderr=cp.stderr,
        )

    return cp

def _normalize_listen_addrs(value: Iterable[str] | str | None) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        trimmed = value.strip()
        if not trimmed:
            return []
        if trimmed.startswith("[") and trimmed.endswith("]"):
            try:
                data = json.loads(trimmed)
                return [str(item).strip() for item in data if str(item).strip()]
            except Exception:
                pass
        parts = [part.strip() for part in re.split(r"[,\s]+", trimmed) if part.strip()]
        return parts
    if isinstance(value, Iterable):
        result: List[str] = []
        for item in value:
            s = str(item).strip()
            if s:
                result.append(s)
        return result
    return []

def categorize_listen_addresses(listen_addrs: Iterable[str] | str | None) -> Tuple[List[str], List[str], List[str]]:
    """Split listen addresses into local, public, and relay buckets."""
    addresses = _normalize_listen_addrs(listen_addrs)
    local: List[str] = []
    public: List[str] = []
    relay: List[str] = []

    for addr in addresses:
        lower = addr.lower()
        if "/p2p-circuit" in lower or "/relay" in lower or "/circuit/" in lower:
            relay.append(addr)
        elif _PRIVATE_IPV4.search(addr) or "/ip6/::1" in lower:
            local.append(addr)
        else:
            public.append(addr)

    return local, public, relay

def _run_actor_command(endpoint: str, *, timeout: int = 30) -> subprocess.CompletedProcess:
    argv = ["nunet", "-c", DMS_DEFAULT_CONTEXT, "actor", "cmd", endpoint]
    return run_dms_command_with_passphrase(
        argv,
        capture_output=True,
        timeout=timeout,
        check=False,
    )


def _run_contract_command(
    endpoint: str,
    *,
    extra_args: Optional[Sequence[str]] = None,
    timeout: int = 30,
) -> Tuple[List[str], subprocess.CompletedProcess]:
    argv: List[str] = ["nunet", "actor", "cmd", "-c", DMS_DEFAULT_CONTEXT, endpoint]
    if extra_args:
        argv.extend([str(arg) for arg in extra_args])
    cp = run_dms_command_with_passphrase(
        argv,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    return argv, cp


def _run_contracts_command(
    args: Sequence[str],
    *,
    timeout: int = 30,
) -> Tuple[List[str], subprocess.CompletedProcess]:
    argv: List[str] = ["nunet", "contracts", "--context", DMS_DEFAULT_CONTEXT]
    argv.extend(str(arg) for arg in args)
    cp = run_dms_command_with_passphrase(
        argv,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    return argv, cp


def _build_contract_result(
    endpoint: str,
    argv: List[str],
    cp: subprocess.CompletedProcess,
    *,
    expect_json: bool = False,
) -> DmsCommandResult:
    stdout = (cp.stdout or "").strip()
    stderr = (cp.stderr or "").strip()
    result: DmsCommandResult = {
        "success": cp.returncode == 0,
        "endpoint": endpoint,
        "argv": argv,
        "returncode": cp.returncode,
        "stdout": stdout,
        "stderr": stderr,
    }
    if cp.returncode != 0:
        result["error"] = stderr or stdout or f"{endpoint} failed with rc={cp.returncode}"
    elif expect_json:
        if not stdout:
            result["success"] = False
            result["error"] = f"{endpoint} returned empty output"
        else:
            try:
                result["data"] = json.loads(stdout)
            except json.JSONDecodeError as exc:
                logger.warning("Invalid JSON from %s: %s", endpoint, exc)
                result["success"] = False
                result["error"] = f"Invalid JSON output from {endpoint}"
    log_level = logging.INFO if result.get("success") else logging.ERROR
    logger.log(
        log_level,
        "DMS contract command %s rc=%s stdout=%s stderr=%s",
        endpoint,
        result.get("returncode"),
        _log_snippet(stdout or "<empty>"),
        _log_snippet(stderr or "<empty>"),
    )
    return result


def _contracts_cli_missing(stderr: str | None, stdout: str | None) -> bool:
    combined = f"{stderr or ''}\n{stdout or ''}".lower()
    return (
        'unknown command "contracts"' in combined
        or "unknown command 'contracts'" in combined
        or "unknown command `contracts`" in combined
    )


def contract_list_incoming(*, timeout: int = 30) -> DmsCommandResult:
    argv, cp = _run_contracts_command(["list", "incoming"], timeout=timeout)
    if cp.returncode == 0 or not _contracts_cli_missing(cp.stderr, cp.stdout):
        return _build_contract_result(
            "contracts list incoming",
            argv,
            cp,
            expect_json=True,
        )
    fallback_argv, fallback_cp = _run_contract_command("/dms/tokenomics/contract/list_incoming", timeout=timeout)
    return _build_contract_result(
        "/dms/tokenomics/contract/list_incoming",
        fallback_argv,
        fallback_cp,
        expect_json=True,
    )


def contract_list_outgoing(*, timeout: int = 30) -> DmsCommandResult:
    argv, cp = _run_contracts_command(["list", "outgoing"], timeout=timeout)
    if cp.returncode != 0 and _contracts_cli_missing(cp.stderr, cp.stdout):
        return {
            "success": False,
            "endpoint": "contracts list outgoing",
            "argv": argv,
            "returncode": cp.returncode,
            "stdout": (cp.stdout or "").strip(),
            "stderr": (cp.stderr or "").strip(),
            "error": (
                "Outgoing contracts require a newer nunet CLI that supports the 'contracts' subcommand. "
                "Please upgrade nunet to list outgoing contracts."
            ),
            "error_code": "contracts_cli_missing",
        }
    return _build_contract_result(
        "contracts list outgoing",
        argv,
        cp,
        expect_json=True,
    )


def contract_state(
    contract_did: str,
    *,
    contract_host_did: Optional[str] = None,
    timeout: int = 30,
) -> DmsCommandResult:
    args = ["--contract-did", contract_did]
    if contract_host_did:
        args.extend(["--contract-host-did", contract_host_did])
    argv, cp = _run_contract_command(
        "/dms/tokenomics/contract/state",
        extra_args=args,
        timeout=timeout,
    )
    return _build_contract_result(
        "/dms/tokenomics/contract/state",
        argv,
        cp,
        expect_json=True,
    )


def contract_create(
    contract_file: str,
    *,
    extra_args: Optional[Sequence[str]] = None,
    timeout: int = 60,
) -> DmsCommandResult:
    args: List[str] = ["--contract-file", contract_file, "--timeout", "1m"]
    if extra_args:
        args.extend([str(arg) for arg in extra_args])
    argv, cp = _run_contract_command(
        "/dms/tokenomics/contract/create",
        extra_args=args,
        timeout=timeout,
    )
    return _build_contract_result(
        "/dms/tokenomics/contract/create",
        argv,
        cp,
        expect_json=False,
    )


def contract_approve_local(
    contract_did: str,
    *,
    extra_args: Optional[Sequence[str]] = None,
    timeout: int = 30,
) -> DmsCommandResult:
    args: List[str] = ["--contract-did", contract_did]
    if extra_args:
        args.extend([str(arg) for arg in extra_args])
    argv, cp = _run_contract_command(
        "/dms/tokenomics/contract/approve_local",
        extra_args=args,
        timeout=timeout,
    )
    return _build_contract_result(
        "/dms/tokenomics/contract/approve_local",
        argv,
        cp,
        expect_json=False,
    )


def contract_terminate(
    contract_did: str,
    *,
    contract_host_did: Optional[str] = None,
    extra_args: Optional[Sequence[str]] = None,
    timeout: int = 30,
) -> DmsCommandResult:
    args: List[str] = ["--contract-did", contract_did]
    if contract_host_did:
        args.extend(["--contract-host-did", contract_host_did])
    if extra_args:
        args.extend([str(arg) for arg in extra_args])
    argv, cp = _run_contract_command(
        "/dms/tokenomics/contract/terminate",
        extra_args=args,
        timeout=timeout,
    )
    return _build_contract_result(
        "/dms/tokenomics/contract/terminate",
        argv,
        cp,
        expect_json=False,
    )

def _call_actor_json(endpoint: str, *, timeout: int = 30) -> Optional[Any]:
    cp = _run_actor_command(endpoint, timeout=timeout)
    if cp.returncode != 0:
        logger.debug(
            "Command %s failed rc=%s: %s",
            endpoint,
            cp.returncode,
            cp.stderr or cp.stdout or "",
        )
        return None

    stdout = (cp.stdout or "").strip()
    if not stdout:
        return None

    try:
        return json.loads(stdout)
    except json.JSONDecodeError as exc:
        logger.warning("Invalid JSON from %s: %s", endpoint, exc)
        return None

def _extract_version(stdout: str) -> Optional[str]:
    for line in (stdout or "").splitlines():
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

def get_dms_status_info() -> Dict[str, Any]:
    """Return the current high-level DMS status information."""
    status: Dict[str, Any] = {
        "dms_status": "Unknown",
        "dms_version": "Unknown",
        "dms_running": "Not Running",
        "dms_context": "Unknown",
        "dms_did": "Unknown",
        "dms_peer_id": "Unknown",
        "dms_is_relayed": None,
    }

    try:
        version_cp = subprocess.run(
            ["nunet", "version"],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        logger.warning("nunet CLI not found while checking DMS version")
        return status

    if version_cp.returncode == 0:
        version = _extract_version(version_cp.stdout or "")
        if version:
            status["dms_version"] = version
        status["dms_status"] = "Installed"
    else:
        logger.debug(
            "nunet version failed rc=%s: %s",
            version_cp.returncode,
            version_cp.stderr or version_cp.stdout or "",
        )
        status["dms_status"] = "Not Installed"

    peer_data = _call_actor_json("/dms/node/peers/self")
    if peer_data:
        status["dms_running"] = "Running"
        status["dms_peer_id"] = peer_data.get("id") or peer_data.get("peer_id") or "Unknown"
        status["dms_context"] = peer_data.get("context") or "dms"
        local_addrs, public_addrs, relay_addrs = categorize_listen_addresses(peer_data.get("listen_addr"))
        status["dms_is_relayed"] = bool(relay_addrs and not public_addrs)

        did_cp = run_dms_command_with_passphrase(
            ["nunet", "key", "did", "dms"],
            capture_output=True,
            check=False,
        )
        if did_cp.returncode == 0 and did_cp.stdout:
            status["dms_did"] = did_cp.stdout.strip()
        else:
            logger.debug(
                "nunet key did dms failed rc=%s: %s",
                did_cp.returncode,
                did_cp.stderr or did_cp.stdout or "",
            )
    else:
        logger.debug("DMS peer info unavailable; service may not be running")

    return status

def _bytes_to_gb(value: int, precision: int = 2) -> float:
    return round(value / (1024 ** 3), precision)

def _fmt_resources(resources_json: Dict[str, Any]) -> str:
    resources = resources_json.get("Resources") or resources_json

    def _safe_int(val: Any) -> int:
        try:
            return int(val)
        except (TypeError, ValueError):
            return 0

    cores = resources.get("cpu", {}).get("cores")
    ram_bytes = _safe_int(resources.get("ram", {}).get("size"))
    disk_bytes = _safe_int(resources.get("disk", {}).get("size"))

    cores_display = cores if cores not in (None, "") else "N/A"
    ram_gb = _bytes_to_gb(ram_bytes)
    disk_gb = _bytes_to_gb(disk_bytes)

    return f"Cores: {cores_display}, RAM: {ram_gb} GB, Disk: {disk_gb} GB"

def _extract_resource_snapshot(payload: Any) -> Dict[str, Any]:
    """
    Normalize resource payloads returned by /dms/node/resources/* into a
    consistent dict with cpu/ram/disk/gpus/etc where available.
    """
    if not isinstance(payload, dict):
        return {}
    resources = payload.get("Resources")
    if isinstance(resources, dict):
        return resources
    return payload


def _coerce_int(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _coerce_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _iter_gpu_entries(value: Any) -> Iterable[Dict[str, Any]]:
    if isinstance(value, list):
        for entry in value:
            if isinstance(entry, dict):
                yield entry
    elif isinstance(value, dict):
        for index, entry in value.items():
            if not isinstance(entry, dict):
                continue
            normalized = dict(entry)
            normalized.setdefault("index", index)
            yield normalized


def _normalize_gpu_entry(entry: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not isinstance(entry, dict):
        return None

    normalized: Dict[str, Any] = {}

    index = _coerce_int(entry.get("index"))
    if index is None:
        index = _coerce_int(entry.get("gpu_index"))
    if index is not None:
        normalized["index"] = index

    make = _coerce_text(entry.get("make")) or _coerce_text(entry.get("vendor"))
    vendor = _coerce_text(entry.get("vendor")) or make
    model = _coerce_text(entry.get("model")) or _coerce_text(entry.get("name"))
    pci_address = (
        _coerce_text(entry.get("pci_address"))
        or _coerce_text(entry.get("pciAddress"))
        or _coerce_text(entry.get("bus_id"))
    )
    uuid = _coerce_text(entry.get("uuid")) or _coerce_text(entry.get("id"))
    vram = _coerce_int(entry.get("vram"))

    if make:
        normalized["make"] = make
    if vendor:
        normalized["vendor"] = vendor
    if model:
        normalized["model"] = model
    if pci_address:
        normalized["pci_address"] = pci_address
    if uuid:
        normalized["uuid"] = uuid
    if vram is not None and vram > 0:
        normalized["vram"] = vram

    return normalized or None


def _extract_hardware_spec_gpus(payload: Any) -> List[Dict[str, Any]]:
    if not isinstance(payload, dict):
        return []

    resources = payload.get("Resources")
    if isinstance(resources, dict):
        gpu_source = resources.get("gpus")
    else:
        gpu_source = payload.get("gpus")

    normalized: List[Dict[str, Any]] = []
    for entry in _iter_gpu_entries(gpu_source):
        candidate = _normalize_gpu_entry(entry)
        if candidate:
            normalized.append(candidate)
    return normalized


def _merge_gpu_metadata(
    resource_snapshot: Dict[str, Any],
    hardware_spec: Any,
) -> Dict[str, Any]:
    merged = dict(resource_snapshot) if isinstance(resource_snapshot, dict) else {}

    current_gpus: List[Dict[str, Any]] = []
    for entry in _iter_gpu_entries(merged.get("gpus")):
        normalized = _normalize_gpu_entry(entry)
        if normalized:
            current_gpus.append(normalized)

    spec_gpus = _extract_hardware_spec_gpus(hardware_spec)
    if not current_gpus:
        if spec_gpus:
            merged["gpus"] = spec_gpus
        return merged

    spec_by_uuid = {gpu.get("uuid"): gpu for gpu in spec_gpus if gpu.get("uuid")}
    spec_by_index = {gpu.get("index"): gpu for gpu in spec_gpus if gpu.get("index") is not None}
    spec_by_pci = {gpu.get("pci_address"): gpu for gpu in spec_gpus if gpu.get("pci_address")}

    final_gpus: List[Dict[str, Any]] = []
    for gpu in current_gpus:
        match = None
        if gpu.get("uuid"):
            match = spec_by_uuid.get(gpu["uuid"])
        if match is None and gpu.get("index") is not None:
            match = spec_by_index.get(gpu["index"])
        if match is None and gpu.get("pci_address"):
            match = spec_by_pci.get(gpu["pci_address"])

        combined = dict(match or {})
        combined.update(gpu)
        if not combined.get("make"):
            combined["make"] = combined.get("vendor")
        if not combined.get("vendor") and combined.get("make"):
            combined["vendor"] = combined["make"]

        final_gpus.append(combined)

    merged["gpus"] = final_gpus
    return merged


def get_dms_resource_info() -> Dict[str, Any]:
    """Return onboarding and resource allocation information."""
    info: Dict[str, Any] = {
        "onboarding_status": "Unknown",
        "free_resources": "Unknown",
        "allocated_resources": "Unknown",
        "onboarded_resources": "Unknown",
        "dms_resources": {},
    }
    raw_snapshots: Dict[str, Any] = {}

    onboarding = _call_actor_json("/dms/node/onboarding/status")
    onboarded = False
    if onboarding is not None:
        onboarded = bool(onboarding.get("onboarded", False))
        info["onboarding_status"] = "ONBOARDED" if onboarded else "NOT ONBOARDED"
    else:
        info["onboarding_status"] = "Unknown"

    if not onboarded:
        placeholder = "N/A (not onboarded)"
        info["free_resources"] = placeholder
        info["allocated_resources"] = placeholder
        info["onboarded_resources"] = placeholder
        return info

    def _load_resource(endpoint: str, label: str) -> str:
        payload = _call_actor_json(endpoint)
        if payload is None:
            return "Unknown"
        raw_snapshots[label] = payload
        try:
            return _fmt_resources(payload)
        except Exception as exc:  # defensive: malformed payloads
            logger.debug("Unable to format %s payload: %s", endpoint, exc)
            return "Unknown"

    info["free_resources"] = _load_resource("/dms/node/resources/free", "free")
    info["allocated_resources"] = _load_resource("/dms/node/resources/allocated", "allocated")
    info["onboarded_resources"] = _load_resource("/dms/node/resources/onboarded", "onboarded")

    # Prefer the onboarded snapshot for detailed hardware information, fall back
    # to allocated/free if onboarded is missing.
    detail_snapshot = (
        raw_snapshots.get("onboarded")
        or raw_snapshots.get("allocated")
        or raw_snapshots.get("free")
        or {}
    )
    resource_snapshot = _extract_resource_snapshot(detail_snapshot)
    hardware_spec_snapshot = _call_actor_json("/dms/node/hardware/spec")
    info["dms_resources"] = _merge_gpu_metadata(resource_snapshot, hardware_spec_snapshot)

    return info

def get_cached_dms_status_info(
    ttl: float = _CACHE_TTL_DEFAULT,
    *,
    force_refresh: bool = False,
) -> Dict[str, Any]:
    if not force_refresh:
        cached = _read_cache(_DMS_STATUS_CACHE, _DMS_STATUS_LOCK, ttl)
        if cached is not None:
            return cached
    info = get_dms_status_info()
    _write_cache(_DMS_STATUS_CACHE, _DMS_STATUS_LOCK, info)
    return deepcopy(info)

def get_cached_dms_resource_info(
    ttl: float = _CACHE_TTL_DEFAULT,
    *,
    force_refresh: bool = False,
) -> Dict[str, Any]:
    if not force_refresh:
        cached = _read_cache(_DMS_RESOURCES_CACHE, _DMS_RESOURCES_LOCK, ttl)
        if cached is not None:
            return cached
    info = get_dms_resource_info()
    _write_cache(_DMS_RESOURCES_CACHE, _DMS_RESOURCES_LOCK, info)
    return deepcopy(info)

def _fetch_peer_snapshot() -> Dict[str, Any]:
    cp = _run_actor_command("/dms/node/peers/list")
    raw_output = cp.stdout or ""

    if cp.returncode != 0:
        logger.debug(
            "peers/list failed rc=%s: %s",
            cp.returncode,
            cp.stderr or raw_output or "",
        )
        return {"peers": [], "raw": raw_output}

    clean_output = _ANSI_RE.sub("", raw_output)
    peers: List[str] = []

    try:
        payload = json.loads(clean_output)
    except json.JSONDecodeError:
        payload = None

    if isinstance(payload, list):
        peers = [str(entry).strip() for entry in payload if str(entry).strip()]
    elif isinstance(payload, dict):
        for key in ("Peers", "peers"):
            value = payload.get(key)
            if isinstance(value, list):
                peers = [str(entry).strip() for entry in value if str(entry).strip()]
                break

    if not peers:
        peers = [line.strip() for line in clean_output.splitlines() if line.strip()]

    return {"peers": peers, "raw": raw_output}

def _get_cached_peer_snapshot(ttl: float, force_refresh: bool = False) -> Dict[str, Any]:
    if not force_refresh:
        cached = _read_cache(_DMS_PEERS_CACHE, _DMS_PEERS_LOCK, ttl)
        if cached is not None:
            if isinstance(cached, list):  # legacy cache shape
                snapshot = {"peers": cached, "raw": ""}
                _write_cache(_DMS_PEERS_CACHE, _DMS_PEERS_LOCK, snapshot)
                return snapshot
            return cached

    snapshot = _fetch_peer_snapshot()
    _write_cache(_DMS_PEERS_CACHE, _DMS_PEERS_LOCK, snapshot)
    return snapshot

def get_cached_dms_peer_list(
    ttl: float = _CACHE_TTL_DEFAULT,
    *,
    force_refresh: bool = False,
) -> List[str]:
    snapshot = _get_cached_peer_snapshot(ttl, force_refresh=force_refresh)
    return deepcopy(snapshot.get("peers", []))

def get_cached_dms_peer_raw(
    ttl: float = _CACHE_TTL_DEFAULT,
    *,
    force_refresh: bool = False,
) -> str:
    snapshot = _get_cached_peer_snapshot(ttl, force_refresh=force_refresh)
    return snapshot.get("raw", "")
def _log_snippet(value: str) -> str:
    if len(value) <= _LOG_OUTPUT_MAX:
        return value
    return f"{value[:_LOG_OUTPUT_MAX]}... [truncated {len(value) - _LOG_OUTPUT_MAX} chars]"
