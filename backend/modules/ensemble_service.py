"""
Service helpers for managing ensembles via the API.
This module replaces the older interactive ensemble manager implementations
with a focused, pure-Python service class that only exposes functionality
required by the FastAPI endpoints.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import yaml

from .ddns_manager import make_dns_label
from .dms_utils import run_dms_command_with_passphrase
from .logging_config import get_logger
from .utils import get_current_branch

logger = get_logger(__name__)

_NUNET_DEPLOYMENTS_DIR = Path("/home/nunet/nunet/deployments")


class EnsembleService:
    """Programmatic helper for ensemble templates and deployments."""

    def __init__(
        self,
        *,
        base_dir: Optional[Path] = None,
        log_dir: Optional[Path] = None,
        deployments_dir: Optional[Path] = None,
    ) -> None:
        home = Path.home()
        self.base_dir = (base_dir or (home / "ensembles")).expanduser()
        self.log_dir = (log_dir or (home / "nunet" / "appliance" / "deployment_logs")).expanduser()
        self.deployments_dir = (deployments_dir or _NUNET_DEPLOYMENTS_DIR).expanduser()

        self.repo = "nunet/solutions/nunet-appliance"
        self.source_dir = "ensembles/examples"

        self._ensure_directories()

    # ------------------------------------------------------------------
    # Filesystem helpers
    # ------------------------------------------------------------------
    def _ensure_directories(self) -> None:
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        logger.debug("Ensured ensemble directories", extra={"base_dir": str(self.base_dir), "log_dir": str(self.log_dir)})

    # ------------------------------------------------------------------
    # DMS helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _run_dms(argv: Sequence[str], *, check: bool = False) -> subprocess.CompletedProcess:
        logger.debug("Executing DMS command", extra={"argv": list(argv), "check": check})
        return run_dms_command_with_passphrase(list(argv), capture_output=True, text=True, check=check)

    def _nunet_actor(self, endpoint: str, *extra: str, check: bool = False) -> subprocess.CompletedProcess:
        argv = ["nunet", "-c", "dms", "actor", "cmd", endpoint]
        argv.extend(extra)
        return self._run_dms(argv, check=check)

    # ------------------------------------------------------------------
    # Deployment discovery & enrichment
    # ------------------------------------------------------------------
    @staticmethod
    def _normalize_timestamp(raw: Any) -> Tuple[str, datetime]:
        dt_value: Optional[datetime] = None

        if isinstance(raw, datetime):
            dt_value = raw
        elif isinstance(raw, (int, float)):
            try:
                dt_value = datetime.fromtimestamp(raw)
            except (OSError, OverflowError, ValueError):
                dt_value = None
        elif isinstance(raw, str):
            ts = raw.strip()
            if ts:
                for candidate in (
                    lambda: datetime.fromisoformat(ts.replace("Z", "+00:00")),
                    lambda: datetime.strptime(ts, "%Y-%m-%d %H:%M:%S"),
                    lambda: datetime.strptime(ts, "%Y/%m/%d %H:%M:%S"),
                    lambda: datetime.strptime(ts, "%d/%m/%Y %H:%M:%S"),
                    lambda: datetime.fromtimestamp(float(ts)),
                ):
                    try:
                        dt_value = candidate()
                        break
                    except Exception:
                        continue

        if dt_value is None:
            dt_value = datetime.now()
        if dt_value.tzinfo is not None:
            dt_value = dt_value.astimezone(timezone.utc).replace(tzinfo=None)

        return dt_value.isoformat(), dt_value

    def _fetch_dms_deployments(self) -> List[Dict[str, Any]]:
        result = self._nunet_actor("/dms/node/deployment/list")
        stdout = (result.stdout or "").strip()
        if result.returncode != 0:
            message = result.stderr or stdout or f"Command failed with rc={result.returncode}"
            raise RuntimeError(message)
        if not stdout:
            return []

        try:
            payload = json.loads(stdout)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Invalid JSON from deployment list: {exc}") from exc

        section = (
            payload.get("Deployments")
            or payload.get("deployments")
            or payload.get("data", {}).get("Deployments")
        )

        deployments: List[Dict[str, Any]] = []
        if isinstance(section, dict):
            for dep_id, info in section.items():
                if not dep_id:
                    continue
                info_dict = info if isinstance(info, dict) else {}
                status = info_dict.get("Status") or info_dict.get("status") or info_dict.get("state")
                timestamp = info_dict.get("Timestamp") or info_dict.get("timestamp")
                iso_ts, dt_ts = self._normalize_timestamp(timestamp)
                deployments.append(
                    {
                        "id": str(dep_id),
                        "status": str(status or "").strip(),
                        "timestamp": iso_ts,
                        "timestamp_dt": dt_ts,
                        "raw": info_dict or info,
                    }
                )
        elif isinstance(section, list):
            for entry in section:
                if not isinstance(entry, dict):
                    continue
                dep_id = (
                    entry.get("ID")
                    or entry.get("Id")
                    or entry.get("id")
                    or entry.get("EnsembleID")
                    or entry.get("ensemble_id")
                )
                if not dep_id:
                    continue
                status = entry.get("Status") or entry.get("status") or entry.get("state")
                timestamp = entry.get("Timestamp") or entry.get("timestamp") or entry.get("UpdatedAt")
                iso_ts, dt_ts = self._normalize_timestamp(timestamp)
                deployments.append(
                    {
                        "id": str(dep_id),
                        "status": str(status or "").strip(),
                        "timestamp": iso_ts,
                        "timestamp_dt": dt_ts,
                        "raw": entry,
                    }
                )
        return deployments

    def parse_deployment_log(self) -> Dict[str, Dict[str, Any]]:
        """Parse ~/nunet/appliance/deployment_logs/deployments.log for history."""
        log_path = self.log_dir / "deployments.log"
        if not log_path.exists():
            return {}

        deployments: Dict[str, Dict[str, Any]] = {}
        try:
            lines = log_path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except Exception as exc:
            logger.warning("Unable to read deployment log", extra={"path": str(log_path), "error": str(exc)})
            return deployments

        i = 0
        while i < len(lines):
            line = lines[i].strip()
            if "Submitting deployment on" in line:
                try:
                    ts_part = line.split("Submitting deployment on ")[1]
                    timestamp_str, file_part = ts_part.split(" for:")
                    file_path = file_part.strip()
                    timestamp = datetime.strptime(timestamp_str.strip(), "%Y-%m-%d %H:%M:%S")
                except Exception:
                    i += 1
                    continue

                success = False
                deployment_id = None
                for j in range(1, 6):
                    if i + j >= len(lines):
                        break
                    lookahead = lines[i + j].strip()
                    if "Ensemble was submitted successfully" in lookahead:
                        success = True
                    match = re.search(r'"EnsembleID"\s*:\s*"?([A-Za-z0-9-]+)"?', lookahead)
                    if match:
                        deployment_id = match.group(1)
                    if "Ensemble deployment unsuccessful" in lookahead:
                        success = False
                        break

                if deployment_id:
                    deployments[deployment_id] = {
                        "timestamp": timestamp,
                        "file_name": file_path,
                        "file_basename": Path(file_path).name,
                        "status": "Submitted" if success else "Failed",
                        "active": False,
                    }
            i += 1
        return deployments

    def get_active_deployments(self) -> Dict[str, str]:
        try:
            deployments = self._fetch_dms_deployments()
        except Exception as exc:
            logger.warning("Failed to fetch deployments", extra={"error": str(exc)})
            return {}

        active: Dict[str, str] = {}
        for item in deployments:
            dep_id = item.get("id")
            if dep_id:
                status = str(item.get("status", "")).strip().lower()
                active[dep_id] = status
        return active

    def _load_ensemble_config(self, deployment_id: str) -> Tuple[Optional[Dict[str, Any]], Optional[Path]]:
        try:
            log_entries = self.parse_deployment_log()
        except Exception as exc:
            logger.warning("Unable to parse deployment log for file lookup", extra={"error": str(exc)})
            log_entries = {}

        entry = log_entries.get(deployment_id)
        if not entry:
            return None, None

        file_name = entry.get("file_name")
        if not file_name:
            return None, None

        path = Path(file_name).expanduser()
        if not path.exists():
            return None, path

        try:
            with path.open("r", encoding="utf-8") as fh:
                data = yaml.safe_load(fh) or {}
            return data, path
        except Exception as exc:
            logger.debug("Failed to load ensemble config %s: %s", path, exc)
            return None, path

    # ------------------------------------------------------------------
    # Public API used by FastAPI routers
    # ------------------------------------------------------------------
    def get_deployments_for_web(self) -> Dict[str, Any]:
        try:
            dms_deployments = self._fetch_dms_deployments()
            deployment_log = self.parse_deployment_log()
        except Exception as exc:
            logger.error("Unable to assemble deployment summary", exc_info=exc)
            return {"status": "error", "message": str(exc), "deployments": [], "count": 0}

        deployments: List[Dict[str, Any]] = []
        for dms in dms_deployments:
            dep_id = dms["id"]
            status = (dms.get("status") or "running").strip().lower() or "running"
            ensemble_info, ensemble_path = self._load_ensemble_config(dep_id)

            deployment_type = ""
            allocations = (ensemble_info or {}).get("allocations") or {}
            if isinstance(allocations, dict):
                for alloc in allocations.values():
                    if isinstance(alloc, dict):
                        alloc_type = str(alloc.get("type") or "").strip()
                        if alloc_type:
                            deployment_type = alloc_type
                            break

            timestamp_iso = dms.get("timestamp")
            if dep_id in deployment_log:
                timestamp_iso = deployment_log[dep_id]["timestamp"].isoformat()
            elif not timestamp_iso:
                timestamp_iso = datetime.now(timezone.utc).isoformat()

            log_entry = deployment_log.get(dep_id, {})
            file_basename = log_entry.get("file_basename")
            candidate_path = None
            if ensemble_path is not None:
                candidate_path = ensemble_path.expanduser()
            elif isinstance(log_entry.get("file_name"), str):
                candidate_path = Path(log_entry["file_name"]).expanduser()

            ensemble_file_relative = ""
            if candidate_path and candidate_path.exists():
                for root in (self.base_dir, self.deployments_dir):
                    try:
                        ensemble_file_relative = str(candidate_path.relative_to(root))
                        break
                    except ValueError:
                        continue
            if not ensemble_file_relative:
                ensemble_file_relative = file_basename or ""

            deployments.append(
                {
                    "id": dep_id,
                    "status": status,
                    "type": deployment_type,
                    "timestamp": timestamp_iso,
                    "ensemble_file": ensemble_file_relative or file_basename or "",
                    "ensemble_file_name": file_basename or "",
                    "ensemble_file_path": str(candidate_path) if candidate_path else "",
                    "ensemble_file_exists": bool(candidate_path and candidate_path.exists()),
                }
            )

        logger.info("Compiled deployment summary", extra={"count": len(deployments)})
        return {"status": "success", "deployments": deployments, "count": len(deployments)}

    def _format_table(self, headers: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
        widths = [len(h) for h in headers]
        for row in rows:
            for idx, cell in enumerate(row):
                widths[idx] = max(widths[idx], len(str(cell)))

        border = "+" + "+".join("-" * (w + 2) for w in widths) + "+"
        header_row = "| " + " | ".join(f"{h:<{w}}" for h, w in zip(headers, widths)) + " |"
        lines = [border, header_row, border]
        for row in rows:
            line = "| " + " | ".join(f"{str(cell):<{w}}" for cell, w in zip(row, widths)) + " |"
            lines.append(line)
        lines.append(border)
        return "\n".join(lines)

    def view_running_ensembles(self) -> Dict[str, Any]:
        active = self.get_active_deployments()
        deployment_log = self.parse_deployment_log()

        combined: Dict[str, Dict[str, Any]] = {}
        for dep_id, status in active.items():
            entry = deployment_log.get(dep_id, {})
            combined[dep_id] = {
                "status": status or "running",
                "active": True,
                "timestamp": entry.get("timestamp", datetime.now()),
                "type": "active",
                "file_name": entry.get("file_name", ""),
            }

        for dep_id, info in deployment_log.items():
            if dep_id in combined:
                continue
            combined[dep_id] = {
                "status": "failed" if info.get("status") != "Submitted" else "completed",
                "active": False,
                "timestamp": info.get("timestamp", datetime.now()),
                "type": "historical",
                "file_name": info.get("file_name", ""),
            }

        items = sorted(combined.items(), key=lambda pair: pair[1]["timestamp"], reverse=True)[:20]

        table_rows = []
        for idx, (dep_id, info) in enumerate(items, 1):
            ts = info["timestamp"]
            ts_str = ts.isoformat() if isinstance(ts, datetime) else str(ts)
            table_rows.append(
                [
                    str(idx),
                    dep_id,
                    info.get("status", ""),
                    "active" if info.get("active") else "historical",
                    Path(info.get("file_name", "")).name or "",
                    ts_str,
                ]
            )

        message = self._format_table(
            ["No.", "Deployment ID", "Status", "Type", "File", "Timestamp"],
            table_rows,
        ) if table_rows else "No deployments recorded."

        return {"status": "success", "items": items, "count": len(items), "message": message}

    def get_deployment_status(self, deployment_id: str) -> Dict[str, str]:
        try:
            active = self.get_active_deployments()
            if deployment_id in active:
                status = active[deployment_id]
                if status in {"completed", "finished", "done", "success"}:
                    return {"status": "success", "deployment_status": "completed", "message": "Deployment completed successfully"}
                if status in {"failed", "error", "cancelled"}:
                    return {"status": "success", "deployment_status": "failed", "message": "Deployment failed"}
                return {"status": "success", "deployment_status": "running", "message": "Deployment is currently running"}

            historical = self.parse_deployment_log()
            if deployment_id in historical:
                info = historical[deployment_id]
                state = "completed" if info.get("status") == "Submitted" else "failed"
                return {"status": "success", "deployment_status": state, "message": f"Deployment {state}"}

            return {"status": "error", "message": f"Deployment {deployment_id} not found"}
        except Exception as exc:
            return {"status": "error", "message": f"Error getting deployment status: {exc}"}

    def get_deployment_manifest_text(self, deployment_id: str) -> Dict[str, str]:
        logger.debug("Retrieving deployment manifest", extra={"deployment_id": deployment_id})
        try:
            result = self._nunet_actor("/dms/node/deployment/manifest", "-i", deployment_id)
            if result.returncode != 0:
                message = result.stderr or result.stdout or "Failed to fetch manifest"
                logger.warning("Manifest fetch failed", extra={"deployment_id": deployment_id, "message": message})
                return {"status": "error", "message": message}
            formatted = self._format_manifest_text(result.stdout or "")
            return {"status": "success", "manifest_text": formatted}
        except Exception as exc:
            logger.exception("Error getting deployment manifest", extra={"deployment_id": deployment_id})
            return {"status": "error", "message": f"Error getting deployment manifest: {exc}"}

    def _format_manifest_text(self, raw: str) -> str:
        if not raw:
            return ""
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return raw

        manifest = payload.get("manifest", {}) if isinstance(payload, dict) else {}
        sections: List[str] = []

        def add_section(title: str, headers: Sequence[str], rows: Sequence[Sequence[str]]):
            if rows:
                sections.append(f"{title}:\n{self._format_table(headers, rows)}")

        details = [
            ["Deployment ID", manifest.get("id", "N/A")],
            ["Ensemble File", manifest.get("ensemble_file", "N/A")],
        ]
        add_section("Deployment Details", ["Field", "Value"], details)

        orchestrator = manifest.get("orchestrator", {})
        orch_rows = [
            ["Host", orchestrator.get("addr", {}).get("host", "N/A")],
            ["Inbox", orchestrator.get("addr", {}).get("inbox", "N/A")],
            ["DID", orchestrator.get("did", {}).get("uri", "N/A")],
            ["Public Key", orchestrator.get("id", {}).get("pub", "N/A")],
        ]
        add_section("Orchestrator", ["Field", "Value"], orch_rows)

        alloc_rows = []
        for alloc_name, alloc in (manifest.get("allocations") or {}).items():
            alloc_rows.append([
                str(alloc_name),
                str(alloc.get("type", "")),
                str(alloc.get("node_id", "")),
                str(alloc.get("dns_name", "")),
                str(alloc.get("priv_addr", "")),
                ", ".join(f"{internal}->{external}" for internal, external in (alloc.get("ports", {}) or {}).items()),
                str(alloc.get("status", "")),
            ])
        add_section(
            "Allocations",
            ["Allocation", "Type", "Node", "DNS", "Private IP", "Ports", "Status"],
            alloc_rows,
        )

        nodes_rows = []
        for node_name, node in (manifest.get("nodes") or {}).items():
            nodes_rows.append([
                node_name,
                node.get("peer", ""),
                ", ".join(node.get("allocations", [])),
            ])
        add_section("Nodes", ["Node", "Peer", "Allocations"], nodes_rows)

        return "\n\n".join(sections) if sections else raw

    def get_deployment_file_content(self, deployment_id: str) -> Dict[str, Any]:
        try:
            log_entries = self.parse_deployment_log()
        except Exception as exc:
            logger.warning("Unable to parse deployment log for file lookup", extra={"error": str(exc)})
            log_entries = {}

        entry = log_entries.get(deployment_id) or {}
        candidates: List[Path] = []

        def add_candidate(value: Any) -> None:
            if isinstance(value, Path):
                candidates.append(value.expanduser())
            elif isinstance(value, str) and value:
                candidates.append(Path(value).expanduser())

        add_candidate(entry.get("file_name"))
        file_basename = entry.get("file_basename")
        if isinstance(file_basename, str) and file_basename:
            add_candidate(self.base_dir / file_basename)
            add_candidate(self.deployments_dir / file_basename)

        _, manifest_path = self._load_ensemble_config(deployment_id)
        add_candidate(manifest_path)

        normalized: List[Path] = []
        seen: set[str] = set()
        for candidate in candidates:
            try:
                resolved = candidate.resolve()
            except Exception:
                resolved = candidate
            key = str(resolved)
            if key not in seen:
                seen.add(key)
                normalized.append(resolved)

        chosen: Optional[Path] = None
        for candidate in normalized:
            if candidate.exists() and candidate.is_file():
                chosen = candidate
                break

        default_name = Path(file_basename).name if isinstance(file_basename, str) else None
        if chosen is None:\r
            logger.info("Deployment file not located", extra={"deployment_id": deployment_id, "candidates": [str(path) for path in normalized]})\r
            return {\r
                "status": "error",\r
                "message": f"Deployment file for {deployment_id} not found",\r
                "exists": False,\r
                "file_name": default_name,\r
                "candidates": [str(path) for path in normalized],\r
            }

        try:
            content = chosen.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            content = chosen.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:
            logger.error("Failed to read deployment file", extra={"path": str(chosen), "error": str(exc)})
            return {
                "status": "error",
                "message": f"Failed to read deployment file: {exc}",
                "file_path": str(chosen),
                "file_name": chosen.name,
                "exists": True,
            }

        relative = None
        for root in (self.base_dir, self.deployments_dir):
            try:
                relative = str(chosen.relative_to(root))
                break
            except Exception:
                continue

        return {
            "status": "success",
            "file_name": chosen.name,
            "file_path": str(chosen),
            "file_relative_path": relative,
            "content": content,
            "exists": True,
        }

    def get_deployment_allocations(self, deployment_id: str) -> List[str]:
        result = self._nunet_actor("/dms/node/deployment/manifest", "-i", deployment_id)
        if result.returncode != 0:
            return []
        try:
            manifest = json.loads(result.stdout or "")
        except json.JSONDecodeError:
            return []
        allocations = manifest.get("manifest", {}).get("allocations", {})
        return list(allocations.keys()) if isinstance(allocations, dict) else []

    def deploy_ensemble(self, file_path: Path, timeout: int = 60) -> Dict[str, Any]:
        self._ensure_directories()
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_path = self.log_dir / "deployments.log"

        try:
            with log_path.open("a", encoding="utf-8") as log:
                log.write(f"Submitting deployment on {timestamp} for: {file_path}\n")
                result = self._nunet_actor(
                    "/dms/node/deployment/new",
                    "-t",
                    f"{timeout}s",
                    "-f",
                    str(file_path),
                    check=True,
                )
                log.write("Ensemble was submitted successfully.\n")
                log.write((result.stdout or "") + "\n")
        except subprocess.CalledProcessError as exc:
            message = f"Ensemble deployment unsuccessful.\nError: {exc}\n"
            logger.error("Deployment command failed", extra={"file_path": str(file_path), "timeout": timeout, "error": str(exc)})
            with log_path.open("a", encoding="utf-8") as log:
                log.write(message)
            return {"status": "error", "message": message}

        deployment_id = None
        for line in (result.stdout or "").splitlines():
            match = re.search(r'"EnsembleID"\s*:\s*"?([A-Za-z0-9-]+)"?', line)
            if match:
                deployment_id = match.group(1)
                break

        logger.info(
            "Submitted ensemble deployment",
            extra={"file_path": str(file_path), "deployment_id": deployment_id, "timeout": timeout},
        )
        return {
            "status": "success",
            "message": "Ensemble was submitted successfully.\n" + (result.stdout or ""),
            "deployment_id": deployment_id,
        }

    def shutdown_deployment(self, deployment_id: str) -> Dict[str, str]:
        logger.info("Requesting deployment shutdown", extra={"deployment_id": deployment_id})
        result = self._nunet_actor("/dms/node/deployment/shutdown", "-i", deployment_id)
        if result.returncode == 0:
            return {"status": "success", "message": f"Successfully shutdown deployment {deployment_id}"}

        error_lines = []
        if result.stdout:
            error_lines.append(f"Output: {result.stdout}")
        if result.stderr:
            error_lines.append(f"Error: {result.stderr}")
        message = "\n".join(error_lines) or "Unknown error shutting down deployment"
        logger.error("Shutdown command failed", extra={"deployment_id": deployment_id, "message": message})
        return {"status": "error", "message": message}

    def get_ensemble_files(self) -> List[Tuple[int, Path]]:
        self._ensure_directories()
        files = sorted(p for p in self.base_dir.rglob("*") if p.is_file())
        return [(idx + 1, path) for idx, path in enumerate(files)]

    def copy_ensemble(self, source: Path, dest: Path) -> Dict[str, str]:
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, dest)
            return {"status": "success", "message": f"File copied from {source.name} to {dest}"}
        except Exception as exc:
            return {"status": "error", "message": f"Error copying file: {exc}"}

    def download_example_ensembles(
        self,
        repo: Optional[str] = None,
        branch: Optional[str] = None,
        source_dir: Optional[str] = None,
        target_dir: Optional[Path] = None,
    ) -> Dict[str, str]:
        repo = repo or self.repo
        source_dir = source_dir or self.source_dir
        target_dir = (target_dir or self.base_dir).expanduser()

        if branch is None:
            try:
                branch = get_current_branch()
            except Exception:
                branch = "main"

        logger.info(
            "Downloading example ensembles",
            extra={"repo": repo, "branch": branch, "source_dir": source_dir, "target_dir": str(target_dir)},
        )

        temp_dir = Path("/tmp/nunet-ensemble-examples")
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)

        try:
            clone = subprocess.run(
                ["git", "clone", "-b", branch, f"https://gitlab.com/{repo}.git", str(temp_dir)],
                capture_output=True,
                text=True,
                check=False,
            )
            if clone.returncode != 0:
                message = clone.stderr or clone.stdout or "git clone failed"
                logger.error("Example ensemble clone failed", extra={"message": message})
                return {"status": "error", "message": f"git clone failed: {message}"}

            source_path = temp_dir / source_dir
            if not source_path.exists():
                logger.error("Example ensemble source directory missing", extra={"source_dir": source_dir})
                return {"status": "error", "message": f"Source directory {source_dir} not found in repository"}

            files_copied = 0
            for item in source_path.iterdir():
                destination = target_dir / item.name
                if item.is_file():
                    shutil.copy2(item, destination)
                else:
                    shutil.copytree(item, destination, dirs_exist_ok=True)
                files_copied += 1

            logger.info("Example ensembles downloaded", extra={"files_copied": files_copied})
            return {"status": "success", "message": f"Copied {files_copied} example files"}
        except Exception as exc:
            logger.exception("Failed to download example ensembles")
            return {"status": "error", "message": f"Failed to download examples: {exc}"}
        finally:
            if temp_dir.exists():
                shutil.rmtree(temp_dir, ignore_errors=True)

    @staticmethod
    def _env_to_dict(env: Any) -> Dict[str, str]:
        if isinstance(env, dict):
            return {str(k): str(v) for k, v in env.items() if v is not None}
        if isinstance(env, Iterable) and not isinstance(env, (str, bytes)):
            items = {}
            for entry in env:
                if isinstance(entry, str) and "=" in entry:
                    k, v = entry.split("=", 1)
                    items[k] = v
            return items
        return {}

    @staticmethod
    def _is_truthy(value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return value != 0
        if isinstance(value, str):
            return value.lower() in {"1", "true", "yes", "on"}
        return False

    def _build_proxy_url(self, env: Dict[str, str], alloc_data: Dict[str, Any], alloc_name: str) -> Optional[str]:
        domain = env.get("DMS_DDNS_URL") or env.get("DYN_DNS_URL")
        if not domain:
            return None

        label = env.get("DMS_PROXY_URL_LABEL") or make_dns_label(alloc_name)
        if not label:
            return None

        scheme = env.get("DMS_PROXY_URL_SCHEME", "https")
        port = env.get("DMS_PROXY_URL_PORT") or alloc_data.get("proxy_port")
        if port:
            return f"{scheme}://{label}.{domain}:{port}"
        return f"{scheme}://{label}.{domain}"

    def enrich_manifest_payload(self, deployment_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(payload, dict):
            return payload
        manifest = payload.get("manifest")
        if not isinstance(manifest, dict):
            return payload

        ensemble_info, ensemble_path = self._load_ensemble_config(deployment_id)
        if ensemble_path and not manifest.get("ensemble_file"):
            manifest["ensemble_file"] = str(ensemble_path)

        allocation_cfgs = (ensemble_info or {}).get("allocations") or {}
        allocations = manifest.get("allocations") or {}
        ddns_map: Dict[str, str] = {}

        if isinstance(allocations, dict):
            for alloc_name, alloc_data in allocations.items():
                if not isinstance(alloc_data, dict):
                    continue
                env_dict: Dict[str, str] = {}
                cfg = allocation_cfgs.get(alloc_name)
                if not cfg and "." in alloc_name:
                    cfg = allocation_cfgs.get(alloc_name.split(".", 1)[-1])
                if not cfg:
                    normalized = alloc_name.replace("-", "_")
                    cfg = allocation_cfgs.get(normalized)
                    if not cfg and "." in normalized:
                        cfg = allocation_cfgs.get(normalized.split(".", 1)[-1])

                if isinstance(cfg, dict):
                    execution = cfg.get("execution") or {}
                    env_dict.update(self._env_to_dict(execution.get("environment")))
                    env_dict.update(self._env_to_dict(execution.get("env")))
                env_dict.update(self._env_to_dict(alloc_data.get("environment")))
                env_dict.update(self._env_to_dict(alloc_data.get("env")))

                requires_proxy = self._is_truthy(env_dict.get("DMS_REQUIRE_PROXY"))
                ddns_enabled = any(
                    self._is_truthy(env_dict.get(key))
                    for key in ("DMS_DDNS_URL", "DYN_DNS_URL", "DMS_DDNS_ENABLED", "ENABLE_DDNS")
                )

                ddns_url = None
                if requires_proxy or ddns_enabled:
                    ddns_url = self._build_proxy_url(env_dict, alloc_data, alloc_name)

                if requires_proxy:
                    alloc_data["requires_proxy"] = True
                if ddns_url:
                    alloc_data["ddns_url"] = ddns_url
                    ddns_map[alloc_name] = ddns_url

        if ddns_map:
            manifest.setdefault("ddns", {}).update(ddns_map)

        return payload












