"""Helper used by the FastAPI ensemble routes."""

import json
import os
import re
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import yaml

from .dms_utils import run_dms_command_with_passphrase
from .ddns_manager import make_dns_label
from .path_constants import APPLIANCE_DEPLOYMENT_LOGS_DIR, DMS_DEPLOYMENTS_DIR, ENSEMBLES_DIR


_STATUS_COMPLETE = {"completed", "complete", "finished", "success", "done"}
_STATUS_FAILED = {"failed", "error", "cancelled", "canceled"}


@dataclass
class _DeploymentEntry:
    deployment_id: str
    status: str
    timestamp_iso: str
    timestamp_dt: datetime
    raw: Dict[str, Any]


class EnsembleManagerV2:
    """Subset of the historical manager used by the API layer."""

    def __init__(self) -> None:
        self.base_dir = ENSEMBLES_DIR
        self.deployments_dir = DMS_DEPLOYMENTS_DIR
        self.log_dir = APPLIANCE_DEPLOYMENT_LOGS_DIR
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.deployments_dir.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.repo = "nunet/solutions/nunet-appliance"
        self.source_dir = "ensembles/examples"

    @staticmethod
    def _run_dms(args: Iterable[str], *, check: bool = True) -> subprocess.CompletedProcess:
        return run_dms_command_with_passphrase(
            ["nunet", "-c", "dms", "actor", "cmd", *args],
            capture_output=True,
            text=True,
            check=check,
        )

    @staticmethod
    def _parse_json(stdout: str) -> Any:
        payload = (stdout or "").strip()
        if not payload:
            return {}
        try:
            return json.loads(payload)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Unable to decode JSON payload: {exc}") from exc

    @staticmethod
    def _coerce_timestamp(value: Any) -> Tuple[str, datetime]:
        if isinstance(value, datetime):
            dt_value = value
        elif isinstance(value, (int, float)):
            dt_value = datetime.fromtimestamp(float(value), tz=timezone.utc)
        elif isinstance(value, str):
            cleaned = value.strip()
            for fmt in ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ"):
                try:
                    dt_value = datetime.strptime(cleaned, fmt).replace(tzinfo=timezone.utc)
                    break
                except ValueError:
                    continue
            else:
                try:
                    dt_value = datetime.fromisoformat(cleaned)
                    if dt_value.tzinfo is None:
                        dt_value = dt_value.replace(tzinfo=timezone.utc)
                except ValueError:
                    dt_value = datetime.now(timezone.utc)
        else:
            dt_value = datetime.now(timezone.utc)

        return dt_value.isoformat(), dt_value

    def _fetch_deployments(self) -> List[_DeploymentEntry]:
        cp = self._run_dms(["/dms/node/deployment/list"])
        payload = self._parse_json(cp.stdout)

        deployments_section = (
            payload.get("Deployments")
            or payload.get("deployments")
            or payload.get("data", {}).get("Deployments")
        )

        entries: List[_DeploymentEntry] = []
        if isinstance(deployments_section, dict):
            iterator = deployments_section.items()
        elif isinstance(deployments_section, list):
            iterator = (
                (
                    item.get("ID")
                    or item.get("Id")
                    or item.get("id")
                    or item.get("EnsembleID")
                    or item.get("ensemble_id"),
                    item,
                )
                for item in deployments_section
                if isinstance(item, dict)
            )
        else:
            iterator = []

        for dep_id, raw in iterator:
            if not dep_id:
                continue
            info = raw if isinstance(raw, dict) else {}
            status = self._extract_status(info)
            timestamp = (
                info.get("Timestamp")
                or info.get("timestamp")
                or info.get("UpdatedAt")
                or info.get("updated_at")
            )
            timestamp_iso, timestamp_dt = self._coerce_timestamp(timestamp)
            entries.append(
                _DeploymentEntry(
                    deployment_id=str(dep_id),
                    status=str(status or "").strip(),
                    timestamp_iso=timestamp_iso,
                    timestamp_dt=timestamp_dt,
                    raw=info,
                )
            )
        return entries

    def _fetch_deployment_status(self, deployment_id: str) -> Dict[str, Any]:
        cp = self._run_dms(
            ["/dms/node/deployment/status", "-i", deployment_id],
            check=False,
        )
        if cp.returncode != 0:
            raise RuntimeError(cp.stderr or cp.stdout or "deployment status command failed")
        detail = self._parse_json(cp.stdout)
        return self._normalize_status_payload(detail)

    def _fetch_manifest(self, deployment_id: str) -> Dict[str, Any]:
        cp = self._run_dms(
            ["/dms/node/deployment/manifest", "-i", deployment_id],
            check=False,
        )
        if cp.returncode != 0:
            raise RuntimeError(cp.stderr or cp.stdout or "deployment manifest command failed")
        return self._parse_json(cp.stdout)

    def _resolve_local_path(self, candidate: Optional[str]) -> Optional[Path]:
        if not candidate:
            return None
        path = Path(str(candidate)).expanduser()
        if path.exists():
            return path
        if not path.is_absolute():
            alt = (self.base_dir / path).resolve()
            if alt.exists():
                return alt
        return None

    def get_deployments_for_web(self) -> Dict[str, Any]:
        try:
            entries = self._fetch_deployments()
            deployment_log = self._parse_deployment_log()
        except Exception as exc:  # pragma: no cover - defensive
            return {"status": "error", "message": str(exc), "deployments": [], "count": 0}

        self._refresh_transient_statuses(entries)

        deployments: List[Dict[str, Any]] = []
        for entry in entries:
            deployment_id = entry.deployment_id
            log_entry = deployment_log.get(deployment_id, {})

            status_text = (entry.status or "").strip().lower()
            if status_text in _STATUS_COMPLETE:
                status_text = "completed"
            elif status_text in _STATUS_FAILED:
                status_text = "failed"
            elif not status_text:
                status_text = "running"

            manifest_data, manifest_path_str, manifest_path = self._load_manifest_info(deployment_id)
            allocations_map = manifest_data.get("allocations") if isinstance(manifest_data, dict) else {}
            allocation_names: List[str] = []
            if isinstance(allocations_map, dict):
                allocation_names = [str(name) for name in allocations_map.keys()]

            ensemble_info, ensemble_path = self._load_ensemble_config(deployment_id, deployment_log)

            template_alloc_cfg: Dict[str, Any] = {}
            template_env_map: Dict[str, str] = {}
            if isinstance(ensemble_info, dict):
                template_alloc_cfg = ensemble_info.get("allocations") or {}
                template_env_map = self._env_to_dict(ensemble_info.get("environment"))
                template_env_map.update(self._env_to_dict(ensemble_info.get("env")))

            self._apply_ddns_details(
                manifest_data,
                allocations_map,
                template_alloc_cfg,
                template_env_map,
            )

            deployment_type = ""
            if isinstance(template_alloc_cfg, dict):
                for alloc in template_alloc_cfg.values():
                    if isinstance(alloc, dict):
                        alloc_type = str(alloc.get("type") or "").strip()
                        if alloc_type:
                            deployment_type = alloc_type
                            break
            if not deployment_type and isinstance(allocations_map, dict):
                for alloc in allocations_map.values():
                    if isinstance(alloc, dict):
                        alloc_type = str(alloc.get("type") or "").strip()
                        if alloc_type:
                            deployment_type = alloc_type
                            break

            timestamp_dt: Optional[datetime] = None
            if isinstance(log_entry.get("timestamp"), datetime):
                timestamp_dt = log_entry["timestamp"]
            elif entry.timestamp_dt:
                timestamp_dt = entry.timestamp_dt
            timestamp_iso = (timestamp_dt or datetime.now(timezone.utc)).isoformat()

            candidate_path: Optional[Path] = None
            if isinstance(ensemble_path, Path) and ensemble_path.exists():
                candidate_path = ensemble_path.expanduser()
            else:
                file_name = log_entry.get("file_name")
                if isinstance(file_name, str) and file_name:
                    potential = Path(file_name).expanduser()
                    if potential.exists():
                        candidate_path = potential

            if not candidate_path and manifest_path and manifest_path.exists():
                candidate_path = manifest_path

            if not candidate_path and manifest_path_str:
                resolved = self._resolve_local_path(manifest_path_str)
                if resolved and resolved.exists():
                    candidate_path = resolved

            ensemble_file_name = ""
            if candidate_path and candidate_path.exists():
                ensemble_file_name = candidate_path.name
            elif isinstance(log_entry.get("file_basename"), str):
                ensemble_file_name = str(log_entry["file_basename"])
            elif isinstance(manifest_path_str, str):
                ensemble_file_name = Path(manifest_path_str).name

            ensemble_file_path = ""
            if candidate_path and candidate_path.exists():
                ensemble_file_path = str(candidate_path)
            elif isinstance(log_entry.get("file_name"), str):
                ensemble_file_path = str(Path(log_entry["file_name"]).expanduser())
            elif isinstance(manifest_path_str, str):
                ensemble_file_path = manifest_path_str
            elif ensemble_file_name:
                ensemble_file_path = ensemble_file_name

            ensemble_file_relative = ""
            if candidate_path and candidate_path.exists():
                for root in (self.base_dir, self.deployments_dir):
                    try:
                        ensemble_file_relative = str(candidate_path.relative_to(root))
                        break
                    except ValueError:
                        continue
            if not ensemble_file_relative:
                if isinstance(log_entry.get("file_name"), str):
                    ensemble_file_relative = str(log_entry["file_name"])
                elif isinstance(manifest_path_str, str):
                    ensemble_file_relative = manifest_path_str
                else:
                    ensemble_file_relative = ensemble_file_name

            deployment_url = self._extract_deployment_url(
                manifest_data,
                allocations_map,
                template_alloc_cfg,
                template_env_map,
            )

            deployments.append(
                {
                    "id": deployment_id,
                    "status": status_text,
                    "type": deployment_type,
                    "timestamp": timestamp_iso,
                    "ensemble_file": ensemble_file_relative or ensemble_file_name,
                    "ensemble_file_name": ensemble_file_name,
                    "ensemble_file_path": ensemble_file_path,
                    "ensemble_file_relative": ensemble_file_relative,
                    "ensemble_file_exists": bool(candidate_path and candidate_path.exists()),
                    "deployment_url": deployment_url,
                    "allocations": allocation_names or None,
                }
            )

        return {
            "status": "success",
            "deployments": deployments,
            "count": len(deployments),
        }

    def _refresh_transient_statuses(self, entries: List[_DeploymentEntry]) -> None:
        transient: List[_DeploymentEntry] = []
        for entry in entries:
            status_lower = (entry.status or "").strip().lower()
            if status_lower in {"", "running", "submitted", "pending", "processing", "in-progress"}:
                transient.append(entry)

        if not transient:
            return

        max_workers = min(4, len(transient))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_map = {
                executor.submit(self._fetch_deployment_status, entry.deployment_id): entry
                for entry in transient
            }
            for future in as_completed(future_map):
                entry = future_map[future]
                try:
                    detail = future.result()
                except Exception:
                    continue

                normalized = self._normalize_status_payload(detail)
                status_lower = ""
                if isinstance(normalized, dict):
                    candidate = (
                        normalized.get("deployment_status")
                        or normalized.get("status")
                        or normalized.get("Status")
                        or normalized.get("state")
                        or normalized.get("State")
                    )
                    if isinstance(candidate, str):
                        status_lower = candidate.strip().lower()
                if not status_lower:
                    status_lower = self._extract_status(detail).lower()

                if status_lower in _STATUS_COMPLETE:
                    entry.status = "completed"
                elif status_lower in _STATUS_FAILED:
                    entry.status = "failed"
                elif status_lower:
                    entry.status = status_lower

    def view_running_ensembles(self) -> Dict[str, Any]:
        try:
            entries = self._fetch_deployments()
        except Exception as exc:  # pragma: no cover - defensive
            return {"status": "error", "message": str(exc), "items": [], "count": 0}

        items: List[Tuple[str, Dict[str, Any]]] = []
        for entry in entries:
            status_lower = entry.status.lower()
            active = status_lower not in _STATUS_COMPLETE | _STATUS_FAILED
            items.append(
                (
                    entry.deployment_id,
                    {
                        "status": entry.status or "unknown",
                        "active": active,
                        "timestamp": entry.timestamp_dt,
                        "type": entry.raw.get("Type") or entry.raw.get("type") or "",
                        "file_name": entry.raw.get("EnsembleFile") or entry.raw.get("ensemble_file") or "",
                    },
                )
            )

        active_count = sum(1 for _, info in items if info.get("active"))
        message = f"{active_count} deployment(s) currently active."

        return {"status": "success", "items": items, "count": len(items), "message": message}

    def get_deployment_status(self, deployment_id: str) -> Dict[str, str]:
        try:
            entries = {entry.deployment_id: entry for entry in self._fetch_deployments()}
            if deployment_id in entries:
                status_lower = entries[deployment_id].status.lower()
                if not status_lower:
                    detail = self._fetch_deployment_status(deployment_id)
                    status_lower = self._extract_status(detail).lower()
                    if not status_lower and isinstance(detail, dict):
                        status_lower = str(detail.get("status") or detail.get("Status") or "").lower()
            else:
                detail = self._fetch_deployment_status(deployment_id)
                status_lower = self._extract_status(detail).lower()
                if not status_lower and isinstance(detail, dict):
                    status_lower = str(detail.get("status") or detail.get("Status") or "").lower()
        except Exception as exc:  # pragma: no cover - defensive
            return {"status": "error", "message": f"Error getting deployment status: {exc}"}

        if status_lower in _STATUS_COMPLETE:
            deployment_status = "completed"
            message = "Deployment completed successfully"
        elif status_lower in _STATUS_FAILED:
            deployment_status = "failed"
            message = "Deployment failed"
        elif status_lower:
            deployment_status = "running"
            message = f"Deployment is currently {status_lower}"
        else:
            deployment_status = "unknown"
            message = "Deployment status is unknown"

        return {"status": "success", "deployment_status": deployment_status, "message": message}

    def get_deployment_allocations(self, deployment_id: str) -> List[str]:
        try:
            detail = self._fetch_deployment_status(deployment_id)
            if isinstance(detail, dict):
                detail = self._normalize_status_payload(detail)
        except Exception:
            return []

        allocations = {}
        if isinstance(detail, dict):
            allocations = detail.get("Allocations") or detail.get("allocations") or {}
            if not allocations:
                nested = detail.get("deployment") or detail.get("Deployment") or detail.get("manifest")
                if isinstance(nested, dict):
                    allocations = nested.get("Allocations") or nested.get("allocations") or {}
        if not allocations:
            manifest_data, _, _ = self._load_manifest_info(deployment_id)
            if isinstance(manifest_data, dict):
                manifest_allocations = manifest_data.get("allocations")
                if isinstance(manifest_allocations, dict):
                    allocations = manifest_allocations

        if isinstance(allocations, dict):
            return [str(name) for name in allocations.keys()]
        if isinstance(allocations, list):
            return [str(item) for item in allocations]
        return []

    def get_deployment_manifest_text(self, deployment_id: str) -> Dict[str, str]:
        try:
            manifest = self._fetch_manifest(deployment_id)
        except Exception as exc:
            return {"status": "error", "message": f"Error getting deployment manifest: {exc}"}

        formatted = json.dumps(manifest, indent=2, sort_keys=True)
        return {"status": "success", "manifest_text": formatted}

    def get_deployment_file_content(self, deployment_id: str) -> Dict[str, Any]:
        manifest_data, manifest_path_str, manifest_path = self._load_manifest_info(deployment_id)

        resolved: Optional[Path] = None
        if manifest_path and manifest_path.exists():
            resolved = manifest_path
        elif manifest_path_str:
            candidate = self._resolve_local_path(manifest_path_str)
            if candidate and candidate.exists():
                resolved = candidate

        if resolved is None:
            deployment_log = self._parse_deployment_log()
            _, log_path = self._load_ensemble_config(deployment_id, deployment_log)
            if log_path and log_path.exists():
                resolved = log_path

        if resolved is None:
            return {
                "status": "error",
                "message": "Deployment file for this deployment could not be found",
                "exists": False,
            }

        try:
            content = resolved.read_text(encoding="utf-8")
        except Exception as exc:  # pragma: no cover - defensive
            return {
                "status": "error",
                "message": f"Failed to read deployment file: {exc}",
                "file_path": str(resolved),
                "file_name": resolved.name,
                "exists": True,
            }

        relative_path = ""
        try:
            relative_path = str(resolved.relative_to(self.base_dir))
        except ValueError:
            relative_path = resolved.name
        if not relative_path and manifest_path_str:
            relative_path = manifest_path_str

        return {
            "status": "success",
            "file_name": resolved.name,
            "file_path": str(resolved),
            "file_relative_path": relative_path,
            "content": content,
            "exists": True,
        }

    def _parse_deployment_log(self) -> Dict[str, Dict[str, Any]]:
        records: Dict[str, Dict[str, Any]] = {}
        log_path = self.log_dir / "deployments.log"
        if not log_path.exists():
            return records

        try:
            lines = log_path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            return records

        total = len(lines)
        index = 0
        while index < total:
            line = lines[index].strip()
            if "Submitting deployment on" in line and " for:" in line:
                try:
                    timestamp_part = line.split("Submitting deployment on ")[1].split(" for:")[0].strip()
                    file_path = line.split(" for: ")[1].strip()
                    timestamp_dt = datetime.strptime(timestamp_part, "%Y-%m-%d %H:%M:%S")
                except (IndexError, ValueError):
                    index += 1
                    continue

                deployment_id: Optional[str] = None
                success = False
                for delta in range(1, 6):
                    offset = index + delta
                    if offset >= total:
                        break
                    neighbour = lines[offset].strip()
                    if '"EnsembleID":' in neighbour:
                        try:
                            deployment_id = neighbour.split('"EnsembleID":')[1].split('"')[1].strip()
                        except IndexError:
                            continue
                    if "Ensemble was submitted successfully" in neighbour:
                        success = True
                    if "Ensemble deployment unsuccessful" in neighbour:
                        success = False
                        break

                if deployment_id:
                    records[deployment_id] = {
                        "timestamp": timestamp_dt,
                        "file_name": file_path,
                        "file_basename": os.path.basename(file_path),
                        "status": "Submitted" if success else "Failed",
                    }
            index += 1
        return records

    def _load_ensemble_config(
        self,
        deployment_id: str,
        deployment_log: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> Tuple[Optional[Dict[str, Any]], Optional[Path]]:
        log_data = deployment_log or {}
        entry = log_data.get(deployment_id)
        if not entry:
            return None, None

        file_name = entry.get("file_name")
        if not isinstance(file_name, str) or not file_name:
            return None, None

        path_resolved = Path(file_name).expanduser()
        if not path_resolved.exists():
            return None, path_resolved

        try:
            data = yaml.safe_load(path_resolved.read_text(encoding="utf-8")) or {}
        except Exception:
            data = None
        return data, path_resolved

    def _load_manifest_info(
        self,
        deployment_id: str,
    ) -> Tuple[Dict[str, Any], Optional[str], Optional[Path]]:
        try:
            manifest_payload = self._fetch_manifest(deployment_id) or {}
        except Exception:
            manifest_payload = {}

        manifest_data: Dict[str, Any] = {}
        if isinstance(manifest_payload, dict):
            manifest_section = manifest_payload.get("manifest")
            if isinstance(manifest_section, dict):
                manifest_data = manifest_section
            else:
                manifest_data = manifest_payload

        manifest_path_str, manifest_path = self._extract_manifest_path(manifest_data)
        if not manifest_path and isinstance(manifest_payload, dict):
            payload_path_str, payload_path = self._extract_manifest_path(manifest_payload)
            if payload_path and payload_path.exists():
                manifest_path = payload_path
                manifest_path_str = manifest_path_str or payload_path_str
            elif not manifest_path_str:
                manifest_path_str = payload_path_str

        return manifest_data, manifest_path_str, manifest_path

    def _extract_manifest_path(
        self,
        manifest_data: Dict[str, Any],
    ) -> Tuple[Optional[str], Optional[Path]]:
        manifest_path = None
        if isinstance(manifest_data, dict):
            manifest_path = manifest_data.get("ensemble_file") or manifest_data.get("EnsembleFile")
            if not manifest_path and isinstance(manifest_data.get("deployment"), dict):
                deployment_section = manifest_data["deployment"]
                manifest_path = deployment_section.get("ensemble_file") or deployment_section.get("EnsembleFile")

        resolved = self._resolve_local_path(manifest_path)
        return manifest_path, resolved

    def _apply_ddns_details(
        self,
        manifest_data: Dict[str, Any],
        allocations_map: Any,
        template_alloc_cfg: Dict[str, Any],
        template_env_map: Dict[str, str],
    ) -> None:
        if not isinstance(manifest_data, dict):
            return

        manifest_env = self._env_to_dict(manifest_data.get("environment"))
        manifest_env.update(self._env_to_dict(manifest_data.get("env")))

        allocations = manifest_data.get("allocations")
        if not isinstance(allocations, dict):
            if isinstance(allocations_map, dict):
                allocations = dict(allocations_map)
                manifest_data["allocations"] = allocations
            else:
                return

        ddns_map: Dict[str, str] = manifest_data.setdefault("ddns", {})
        for alloc_name, alloc in allocations.items():
            if not isinstance(alloc, dict):
                continue

            env_map = dict(template_env_map)

            cfg = None
            if isinstance(template_alloc_cfg, dict):
                cfg = template_alloc_cfg.get(alloc_name)
                if not cfg and "." in alloc_name:
                    cfg = template_alloc_cfg.get(alloc_name.split(".", 1)[-1])
            if isinstance(cfg, dict):
                env_map.update(self._env_to_dict(cfg.get("environment")))
                env_map.update(self._env_to_dict(cfg.get("env")))
                execution = cfg.get("execution") or {}
                env_map.update(self._env_to_dict(execution.get("environment")))
                env_map.update(self._env_to_dict(execution.get("env")))

            env_map.update(manifest_env)
            env_map.update(self._env_to_dict(alloc.get("environment")))
            env_map.update(self._env_to_dict(alloc.get("env")))

            ddns_url = alloc.get("ddns_url")
            if not ddns_url:
                ddns_url = self._build_proxy_url(env_map, alloc, alloc_name)
            if isinstance(ddns_url, str):
                ddns_url = ddns_url.strip()
            if ddns_url:
                alloc["ddns_url"] = ddns_url
                ddns_map[alloc_name] = ddns_url

        for key in list(ddns_map.keys()):
            if not ddns_map[key]:
                ddns_map.pop(key, None)

    def _extract_deployment_url(
        self,
        manifest_data: Dict[str, Any],
        allocations_map: Any,
        template_alloc_cfg: Dict[str, Any],
        template_env_map: Dict[str, str],
    ) -> Optional[str]:
        self._apply_ddns_details(
            manifest_data,
            allocations_map,
            template_alloc_cfg,
            template_env_map,
        )

        if isinstance(manifest_data, dict):
            direct = manifest_data.get("deployment_url")
            if isinstance(direct, str) and direct.strip():
                return direct.strip()

            ddns = manifest_data.get("ddns")
            if isinstance(ddns, dict):
                for value in ddns.values():
                    if isinstance(value, str) and value.strip():
                        return value.strip()

        if isinstance(allocations_map, dict):
            for alloc in allocations_map.values():
                if not isinstance(alloc, dict):
                    continue
                ddns_url = alloc.get("ddns_url")
                if isinstance(ddns_url, str) and ddns_url.strip():
                    return ddns_url.strip()
        return None

    @staticmethod
    def _is_truthy(value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if value is None:
            return False
        return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}

    @classmethod
    def _env_to_dict(cls, env: Any) -> Dict[str, str]:
        env_map: Dict[str, str] = {}
        if env is None:
            return env_map
        if isinstance(env, dict):
            for key, val in env.items():
                if key is None:
                    continue
                env_map[str(key).strip().upper()] = "" if val is None else str(val).strip()
            return env_map
        if isinstance(env, str):
            if "=" in env:
                key, val = env.split("=", 1)
                env_map[key.strip().upper()] = val.strip()
            return env_map
        if isinstance(env, (list, tuple, set)):
            for item in env:
                env_map.update(cls._env_to_dict(item))
            return env_map
        return env_map

    @staticmethod
    def _split_container_name(name: str, fallback_suffix: str) -> Tuple[str, str]:
        if not name:
            base = fallback_suffix or "alloc"
            return base, base
        base = name
        suffix = fallback_suffix or "alloc"
        if "_" in name:
            base, suffix_candidate = name.rsplit("_", 1)
            suffix = suffix_candidate or suffix
        elif "-" in name:
            base, suffix_candidate = name.rsplit("-", 1)
            suffix = suffix_candidate or suffix
        base = base or fallback_suffix or "alloc"
        suffix = suffix or fallback_suffix or "alloc"
        return base, suffix

    @staticmethod
    def _port_is_default(port: Any, scheme: str) -> bool:
        if port is None:
            return True
        try:
            port_int = int(str(port).strip())
        except (TypeError, ValueError):
            return False
        scheme = (scheme or "").lower()
        if scheme == "https":
            return port_int == 443
        if scheme == "http":
            return port_int == 80
        return False

    @staticmethod
    def _build_proxy_url(env: Dict[str, str], alloc_data: Dict[str, Any], alloc_name: str) -> Optional[str]:
        env = dict(env or {})
        proxy_url = (
            env.get("DMS_PROXY_URL")
            or env.get("HAGALL_PUBLIC_ENDPOINT")
            or env.get("PUBLIC_ENDPOINT")
        )
        scheme = (env.get("DMS_PROXY_SCHEME") or env.get("DMS_PROXY_PROTOCOL") or "https").lower()
        port = env.get("DMS_PROXY_PORT") or env.get("PROXY_PORT")
        domain = env.get("DMS_DDNS_DOMAIN") or env.get("DYN_DNS_DOMAIN")
        dns_name = (
            alloc_data.get("dns_name")
            or env.get("DMS_DDNS_NAME")
            or env.get("DNS_NAME")
            or alloc_name
        )

        if proxy_url:
            proxy_url = str(proxy_url).strip()
            if not proxy_url:
                return None
            if not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", proxy_url):
                host = proxy_url
                if port and not EnsembleManagerV2._port_is_default(port, scheme):
                    host_part = host.split("/", 1)[0]
                    if ":" not in host_part:
                        host = f"{host}:{port}"
                proxy_url = f"{scheme}://{host}"
            return proxy_url

        host = None
        host_placeholder = False
        if dns_name:
            dns_name = str(dns_name).strip()
            if dns_name:
                lower_dns = dns_name.lower()
                if "." not in dns_name:
                    if domain:
                        host = f"{dns_name}.{domain}"
                    else:
                        host = dns_name
                        host_placeholder = True
                else:
                    host = dns_name
                    host_placeholder = any(
                        lower_dns.endswith(suffix) for suffix in (".internal", ".local", ".lan")
                    ) or lower_dns in {"localhost", alloc_name.lower()}

        ddns_enabled = any(
            EnsembleManagerV2._is_truthy(env.get(key))
            for key in ("DMS_DDNS_URL", "DYN_DNS_URL", "DMS_DDNS_ENABLED", "ENABLE_DDNS")
        )

        allocation_identifier = None
        if ddns_enabled:
            allocation_identifier = (
                alloc_data.get("id")
                or env.get("DMS_ALLOCATION_ID")
                or env.get("ALLOCATION_ID")
            )
        if ddns_enabled and allocation_identifier:
            base, suffix = EnsembleManagerV2._split_container_name(str(allocation_identifier), alloc_name)
            label = make_dns_label(base, suffix)
            fallback_domain = domain or "ddns.nunet.network"
            candidate_host = f"{label}.{fallback_domain}"
            if host is None or host_placeholder:
                host = candidate_host

        if host:
            host = host.strip()
            if not host:
                return None
            if not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", host):
                host_part = host
                if ddns_enabled:
                    scheme = "https"
                elif port and not EnsembleManagerV2._port_is_default(port, scheme):
                    leading = host_part.split("/", 1)[0]
                    if ":" not in leading:
                        host_part = f"{host_part}:{port}"
                host = f"{scheme}://{host_part}"
            return host

        return None

    @staticmethod
    def _normalize_status_payload(payload: Any) -> Any:
        """Reduce common DMS payload wrappers to the first mapping we care about."""
        if isinstance(payload, dict):
            for key in ("deployment", "Deployment", "data", "Data", "result", "Result"):
                value = payload.get(key)
                if isinstance(value, dict):
                    return value
        return payload

    @staticmethod
    def _extract_status(payload: Any) -> str:
        """Return the first non-empty status/state string found in *payload*."""
        if isinstance(payload, str):
            return payload.strip()
        if isinstance(payload, dict):
            for key in ("status", "Status", "state", "State"):
                value = payload.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
            for value in payload.values():
                found = EnsembleManagerV2._extract_status(value)
                if found:
                    return found
        elif isinstance(payload, list):
            for item in payload:
                found = EnsembleManagerV2._extract_status(item)
                if found:
                    return found
        return ""

    def deploy_ensemble(self, file_path: Path, timeout: int = 60) -> Dict[str, str]:
        try:
            file_path = file_path.expanduser()
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            log_path = self.log_dir / "deployments.log"

            try:
                with log_path.open("a", encoding="utf-8") as log:
                    log.write(f"Submitting deployment on {timestamp} for: {file_path}\n")
            except OSError:
                pass

            cp = self._run_dms(
                [
                    "/dms/node/deployment/new",
                    "-t",
                    f"{int(timeout)}s",
                    "-f",
                    str(file_path),
                ],
                check=False,
            )
        except Exception as exc:  # pragma: no cover - defensive
            try:
                with (self.log_dir / "deployments.log").open("a", encoding="utf-8") as log:
                    log.write(f"Ensemble deployment unsuccessful.\nError: {exc}\n")
            except OSError:
                pass
            return {"status": "error", "message": f"Failed to submit deployment: {exc}"}

        if cp.returncode != 0:
            try:
                with (self.log_dir / "deployments.log").open("a", encoding="utf-8") as log:
                    log.write("Ensemble deployment unsuccessful.\n")
                    log.write(cp.stderr or cp.stdout or "Deployment submission failed")
                    log.write("\n")
            except OSError:
                pass
            return {"status": "error", "message": cp.stderr or cp.stdout or "Deployment submission failed"}

        deployment_id = None
        match = re.search(r'"EnsembleID"\s*:\s*"([^"]+)"', cp.stdout or "")
        if match:
            deployment_id = match.group(1)

        try:
            with (self.log_dir / "deployments.log").open("a", encoding="utf-8") as log:
                log.write("Ensemble was submitted successfully.\n")
                if cp.stdout:
                    log.write(cp.stdout)
                    if not cp.stdout.endswith("\n"):
                        log.write("\n")
        except OSError:
            pass

        return {
            "status": "success",
            "message": cp.stdout,
            "deployment_id": deployment_id,
        }

    def shutdown_deployment(self, deployment_id: str) -> Dict[str, str]:
        try:
            cp = self._run_dms(
                ["/dms/node/deployment/shutdown", "-i", deployment_id],
                check=False,
            )
        except Exception as exc:  # pragma: no cover - defensive
            return {"status": "error", "message": f"Failed to shut down deployment: {exc}"}

        if cp.returncode != 0:
            return {"status": "error", "message": cp.stderr or cp.stdout or "Shutdown failed"}

        return {"status": "success", "message": cp.stdout or "Deployment shutdown requested"}

    def get_ensemble_files(self) -> List[Tuple[int, Path]]:
        files = sorted(p for p in self.base_dir.rglob("*") if p.is_file())
        return [(idx + 1, path) for idx, path in enumerate(files)]

    def copy_ensemble(self, source: Path, dest: Path) -> Dict[str, str]:
        source = source.expanduser()
        dest = dest.expanduser()

        if not source.exists():
            return {"status": "error", "message": f"Source file not found: {source}"}

        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, dest)
            return {"status": "success", "message": f"Copied to {dest}"}
        except Exception as exc:  # pragma: no cover - defensive
            return {"status": "error", "message": f"Failed to copy template: {exc}"}

    def download_example_ensembles(self, *, repo: Optional[str] = None, branch: Optional[str] = None, source_dir: Optional[str] = None) -> Dict[str, str]:
        """
        Placeholder implementation.  In this trimmed manager we simply report
        that the operation is not supported, keeping API compatibility without
        performing network operations.
        """
        return {
            "status": "success",
            "message": "Example ensemble download is not available in this build.",
        }

    def enrich_manifest_payload(self, deployment_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(payload, dict):
            return payload

        manifest = payload.get("manifest")
        if not isinstance(manifest, dict):
            return payload

        if not manifest.get("ensemble_file"):
            manifest_file = self._resolve_local_path(manifest.get("ensemble_file"))
            if manifest_file:
                manifest["ensemble_file"] = str(manifest_file)

        deployment_log = self._parse_deployment_log()
        ensemble_info, _ = self._load_ensemble_config(deployment_id, deployment_log)

        template_alloc_cfg: Dict[str, Any] = {}
        template_env_map: Dict[str, str] = {}
        if isinstance(ensemble_info, dict):
            template_alloc_cfg = ensemble_info.get("allocations") or {}
            template_env_map = self._env_to_dict(ensemble_info.get("environment"))
            template_env_map.update(self._env_to_dict(ensemble_info.get("env")))

        allocations_map = manifest.get("allocations")
        self._apply_ddns_details(
            manifest,
            allocations_map,
            template_alloc_cfg,
            template_env_map,
        )

        return payload
