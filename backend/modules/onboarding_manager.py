"""
FastAPI-focused onboarding manager.

This module intentionally strips the legacy terminal menu and Flask web-manager
behaviour.  Only the features exercised by the current FastAPI routers are
implemented here: state tracking, onboarding API hand-offs, capability
anchoring, certificate management, and service restarts.
"""

import json
import logging
import os
import re
import subprocess
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional, List

import requests

from .dms_manager import DMSManager
from .dms_utils import get_dms_resource_info, run_dms_command_with_passphrase
from .org_utils import load_known_organizations, extract_role_profiles, get_tokens_for_org
from .path_constants import (
    APPLIANCE_DIR,
    DMS_CAP_FILE,
    KNOWN_ORGS_FILE,
    NUNET_CONFIG_PATH,
    ONBOARDING_LOG_FILE,
    ONBOARDING_STATE_FILE,
    SERVICE_DMS_CAP_FILE,
)
from .caddy_proxy_manager import CaddyProxyManager

logger = logging.getLogger(__name__)

_ANSI_RE = re.compile(r"\x1B\[[0-9;]*m")


def _timestamp() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


def _deep_copy(data: Dict[str, Any]) -> Dict[str, Any]:
    try:
        return json.loads(json.dumps(data))
    except Exception:
        return dict(data)


def _env_int(name: str, default: int, *, minimum: int = 1) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return max(minimum, int(raw))
    except ValueError:
        logger.warning("Invalid integer for %s=%r; using default %s", name, raw, default)
        return default


def _env_float(name: str, default: float, *, minimum: float = 0.1) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return max(minimum, float(raw))
    except ValueError:
        logger.warning("Invalid float for %s=%r; using default %s", name, raw, default)
        return default


ONBOARDING_STATUS_ATTEMPTS = _env_int("NUNET_ONBOARDING_STATUS_ATTEMPTS", 24)
ONBOARDING_STATUS_DELAY_SEC = _env_float("NUNET_ONBOARDING_STATUS_DELAY_SEC", 5.0)


class OnboardingManager:
    _STATE_DIR = APPLIANCE_DIR
    STATE_PATH = ONBOARDING_STATE_FILE
    LOG_PATH = ONBOARDING_LOG_FILE

    def __init__(
        self,
        *,
        session: Optional[requests.Session] = None,
        use_mock_api: bool = False,
    ) -> None:
        self.session = session or requests.Session()
        self.use_mock_api = use_mock_api
        self.dms_manager = DMSManager()
        self.state: Dict[str, Any] = self._load_state()
        self.caddy_proxy_manager = CaddyProxyManager()

    @staticmethod
    def _baseline_state() -> Dict[str, Any]:
        return {
            "step": "init",
            "progress": 0,
            "wormhole_code": None,
            "org_data": None,
            "form_data": {},
            "error": None,
            "logs": [],
            "api_status": None,
            "api_payload": None,
            "request_id": None,
            "status_token": None,
            "processing": False,
            "processed_ok": False,
            "completed": False,
            # Contract-enabled flow fields
            "contract_caps_applied": False,
            "contract_caps": None,
            "deployment_caps_applied": False,
            "deployment_caps": None,
            "contract_signed": False,
            "contract_did": None,
            "contract_data": None,
            "seen_contract_dids": [],
        }

    @staticmethod
    def _is_onboarded_status(value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            cleaned = _ANSI_RE.sub("", value).strip().upper()
            return cleaned == "ONBOARDED"
        return False

    def _wait_for_onboarded(
        self,
        attempts: Optional[int] = None,
        delay: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        After running the onboarding script, poll the DMS until the node reports
        itself as ONBOARDED (or we give up). Returns the latest snapshot.
        """
        max_attempts = max(1, int(attempts if attempts is not None else ONBOARDING_STATUS_ATTEMPTS))
        poll_delay = max(0.1, float(delay if delay is not None else ONBOARDING_STATUS_DELAY_SEC))
        latest: Dict[str, Any] = {}
        for attempt in range(1, max_attempts + 1):
            if attempt > 1:
                time.sleep(poll_delay)
            latest = get_dms_resource_info()
            if self._is_onboarded_status(latest.get("onboarding_status")):
                if attempt > 1:
                    self.append_log(
                        "submit_data",
                        f"Compute onboarding reported ONBOARDED after {attempt} checks.",
                    )
                return latest

            if attempt in (1, max_attempts):
                status_display = latest.get("onboarding_status", "Unknown")
                self.append_log(
                    "submit_data",
                    f"Onboarding status check {attempt}/{max_attempts}: {status_display}",
                )
        return latest

    # ------------------------------------------------------------------ #
    # State helpers
    # ------------------------------------------------------------------ #

    def _load_state(self) -> Dict[str, Any]:
        if not self.STATE_PATH.exists():
            return self._baseline_state()
        try:
            raw = json.loads(self.STATE_PATH.read_text())
            if not isinstance(raw, dict):
                raise ValueError("Stored onboarding state is not a mapping")
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Unable to read onboarding state; recreating blank one: %s", exc)
            return self._baseline_state()
        raw.setdefault("logs", [])
        raw.setdefault("completed", False)
        return raw

    def _write_state(self) -> None:
        self.STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.STATE_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.state, indent=2))
        tmp.replace(self.STATE_PATH)

    def save_state(self) -> None:
        """Persist the current in-memory state."""
        self._write_state()

    def load_state(self) -> Dict[str, Any]:
        """Reload state from disk (mainly for compatibility with older callers)."""
        self.state = self._load_state()
        return self.state

    # ------------------------------------------------------------------ #
    # Logging & mutation
    # ------------------------------------------------------------------ #

    def append_log(self, step: str, message: str, *, only_on_step_change: bool = False) -> None:
        logs = self.state.setdefault("logs", [])
        if only_on_step_change and logs:
            last = logs[-1]
            if last.get("step") == step:
                return

        entry = {"timestamp": _timestamp(), "step": step, "message": message}
        logs.append(entry)

        try:
            self.LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
            with self.LOG_PATH.open("a", encoding="utf-8") as fh:
                fh.write(f"[{entry['timestamp']}] [{step}] {message}\n")
        except Exception as exc:  # pragma: no cover - best effort
            logger.debug("Unable to append onboarding log to %s: %s", self.LOG_PATH, exc)

        self._write_state()

    def update_state(self, **kwargs: Any) -> Dict[str, Any]:
        """Merge *kwargs* into the state and persist it."""
        if not isinstance(self.state, dict):
            self.state = self._baseline_state()

        old_step = self.state.get("step")
        new_step = kwargs.get("step", old_step)

        self.state.update(kwargs)

        if new_step and new_step != old_step:
            self.append_log(str(new_step), f"Step changed to {new_step}", only_on_step_change=True)
        else:
            self._write_state()

        return self.state

    def clear_state(self) -> None:
        """Reset onboarding state and remove persisted artefacts."""
        self.state = self._baseline_state()
        if self.STATE_PATH.exists():
            try:
                self.STATE_PATH.unlink()
            except Exception:
                logger.debug("Failed to delete onboarding state file.", exc_info=True)
        if self.LOG_PATH.exists():
            try:
                self.LOG_PATH.unlink()
            except Exception:
                logger.debug("Failed to delete onboarding log file.", exc_info=True)
        self._write_state()

    def get_onboarding_status(self) -> Dict[str, Any]:
        """Return a serialisable copy of the current state."""
        return _deep_copy(self.state)

    # ------------------------------------------------------------------ #
    # Role / permission helpers
    # ------------------------------------------------------------------ #

    def get_selected_role_id(self) -> Optional[str]:
        """Return the currently selected role identifier, if available."""
        org_data = self.state.get("org_data") or {}
        org_did = None
        if isinstance(org_data, dict):
            org_did = org_data.get("did")
            selected = org_data.get("selected_role")
            if isinstance(selected, str) and selected.strip():
                return selected.strip()

        form_data = self.state.get("form_data") or {}
        if isinstance(form_data, dict):
            roles = form_data.get("roles")
            if isinstance(roles, (list, tuple, set)):
                for role in roles:
                    if role is None:
                        continue
                    value = role.strip() if isinstance(role, str) else str(role).strip()
                    if value:
                        return value
            selected = form_data.get("why_join")
            if isinstance(selected, str) and selected.strip():
                return selected.strip()

        roles = org_data.get("roles")
        if isinstance(roles, list):
            for role in roles:
                if isinstance(role, str) and role.strip():
                    return role.strip()

        if isinstance(org_did, str) and org_did.strip():
            try:
                from backend.nunet_api import role_metadata

                primary = role_metadata.get_primary_role(org_did)
                if primary:
                    return primary

                cached_roles = role_metadata.get_roles(org_did)
                if cached_roles:
                    return cached_roles[0]
            except Exception as exc:  # pragma: no cover - defensive log path
                logger.debug("Unable to load cached role metadata: %s", exc)

        return None

    def get_role_profiles(self) -> Dict[str, Dict[str, Any]]:
        """
        Retrieve cached role profiles for the selected organisation, falling
        back to the known organisations payload when necessary.
        """
        org_data = self.state.get("org_data") or {}
        profiles = org_data.get("role_profiles")
        if isinstance(profiles, dict) and profiles:
            return profiles

        org_did = org_data.get("did")
        if not isinstance(org_did, str) or not org_did:
            return {}

        try:
            known = load_known_organizations() or {}
            entry = known.get(org_did)
            profiles = extract_role_profiles(entry)
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug("Failed to load role profiles for %s: %s", org_did, exc)
            profiles = {}

        if profiles:
            updated = dict(org_data)
            updated["role_profiles"] = profiles
            self.update_state(org_data=updated)
        return profiles

    def get_active_role_profile(self) -> Dict[str, Any]:
        """Return the complete role profile for the active role."""
        role_id = self.get_selected_role_id()
        if not role_id:
            return {}
        profiles = self.get_role_profiles()
        profile = profiles.get(role_id)
        if isinstance(profile, dict):
            return profile
        return {}

    @staticmethod
    def _normalize_cap_value(value: str) -> str:
        """Normalize a capability string for reliable comparisons."""
        normalized = value.strip()
        if not normalized:
            return ""
        if not normalized.startswith("/"):
            normalized = f"/{normalized}"
        return normalized.rstrip("/")

    @classmethod
    def _extract_caps(cls, require_template: Dict[str, Any] | None) -> List[str]:
        """Return a normalised list of capability paths from a require template."""
        if not isinstance(require_template, dict):
            return []
        raw_caps = require_template.get("caps")
        if not isinstance(raw_caps, list):
            return []
        caps: List[str] = []
        for cap in raw_caps:
            if not isinstance(cap, str):
                continue
            normalized = cls._normalize_cap_value(cap)
            if normalized and normalized not in caps:
                caps.append(normalized)
        return caps

    @staticmethod
    def _extract_topics(require_template: Dict[str, Any] | None) -> List[str]:
        """Return a de-duplicated list of topic strings from a require template."""
        if not isinstance(require_template, dict):
            return []
        raw_topics = require_template.get("topics")
        if not isinstance(raw_topics, list):
            return []
        topics: List[str] = []
        for topic in raw_topics:
            if not isinstance(topic, str):
                continue
            clean_topic = topic.strip()
            if clean_topic and clean_topic not in topics:
                topics.append(clean_topic)
        return topics

    def _cache_role_profile(self, org_did: str, role_id: str, profile: Dict[str, Any]) -> None:
        """Persist an updated role profile in the onboarding state."""
        if not org_did or not role_id or not isinstance(profile, dict):
            return
        org_data = self.state.get("org_data")
        if not isinstance(org_data, dict) or org_data.get("did") != org_did:
            return
        updated_org_data = dict(org_data)
        existing_profiles = updated_org_data.get("role_profiles")
        if isinstance(existing_profiles, dict):
            merged_profiles = dict(existing_profiles)
        else:
            merged_profiles = {}
        merged_profiles[role_id] = dict(profile)
        updated_org_data["role_profiles"] = merged_profiles
        self.update_state(org_data=updated_org_data)

    @staticmethod
    def _known_orgs_candidates() -> List[Path]:
        return [KNOWN_ORGS_FILE]

    @classmethod
    def _active_known_orgs_path(cls) -> Optional[Path]:
        for candidate in cls._known_orgs_candidates():
            if candidate.exists():
                return candidate
        return None

    def _load_role_profile_from_known(self, org_did: str, role_id: Optional[str]) -> Dict[str, Any]:
        """Refresh the role profile for *role_id* from the known organizations data."""
        if not org_did or not role_id:
            return {}
        try:
            known = load_known_organizations() or {}
            entry = known.get(org_did)
            if not entry:
                return {}
            source_path = self._active_known_orgs_path()
            logger.info(
                "Loaded known organizations for org=%s from %s",
                org_did,
                source_path or "<not found>",
            )
            profiles = extract_role_profiles(entry)
            profile = profiles.get(role_id)
            if isinstance(profile, dict):
                logger.info(
                    "Refreshed role profile for org=%s role=%s from known organizations.",
                    org_did,
                    role_id,
                )
                self._cache_role_profile(org_did, role_id, profile)
                return dict(profile)
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug("Unable to refresh role profile for %s/%s: %s", org_did, role_id, exc)
        return {}

    def get_active_caps(self) -> List[str]:
        """Expose the capability list for the active role profile."""
        profile = self.get_active_role_profile()
        require_template = profile.get("require_template") if isinstance(profile, dict) else None
        return self._extract_caps(require_template)

    @classmethod
    def _cap_allows(cls, granted: str, required: str) -> bool:
        """Determine if *granted* capability covers the *required* path."""
        granted_norm = cls._normalize_cap_value(granted)
        required_norm = cls._normalize_cap_value(required)
        if not granted_norm or not required_norm:
            return False
        if granted_norm == "/dms":
            return True
        if granted_norm == required_norm:
            return True
        return required_norm.startswith(f"{granted_norm}/")

    def role_allows(self, permission: str, *, default: bool = False) -> bool:
        """
        Check if the active role grants a specific permission.
        Permissions are derived from the capability set in require_template.
        """
        caps = self.get_active_caps()
        if not caps:
            return default

        if permission == "deploy":
            required_cap = "/dms/deployment"
            return any(self._cap_allows(cap, required_cap) for cap in caps)

        return default

    # ------------------------------------------------------------------ #
    # External metadata helpers
    # ------------------------------------------------------------------ #

    def get_onboarding_api_url(self) -> Optional[str]:
        """Resolve the onboarding API URL for the selected organisation."""
        org_data = self.state.get("org_data") or {}
        org_did = org_data.get("did") if isinstance(org_data, dict) else None
        if not org_did:
            return None

        known = load_known_organizations() or {}
        entry = known.get(org_did)
        if isinstance(entry, dict):
            return entry.get("onboarding_api_url") or entry.get("api_url")
        if isinstance(entry, str):
            return entry
        return None

    # ------------------------------------------------------------------ #
    # Upstream API interactions
    # ------------------------------------------------------------------ #

    def _ensure_pre_onboarding(self) -> Dict[str, Any]:
        """
        Ensure the local node is onboarded before sending join payloads.
        Returns the latest DMS resource snapshot.
        """
        info = get_dms_resource_info()
        status_raw = info.get("onboarding_status")
        if self._is_onboarded_status(status_raw):
            return info

        self.append_log("submit_data", "Running compute onboarding to refresh resources...")
        result = self.dms_manager.onboard_compute()
        if result.get("status") != "success":
            message = result.get("message", "Compute onboarding failed")
            raise RuntimeError(message)
        wait_window_sec = int(round(ONBOARDING_STATUS_ATTEMPTS * ONBOARDING_STATUS_DELAY_SEC))
        self.append_log(
            "submit_data",
            "Compute onboarding script finished. "
            f"Waiting for DMS to report ONBOARDED (up to {ONBOARDING_STATUS_ATTEMPTS} checks / ~{wait_window_sec}s)...",
        )

        refreshed = self._wait_for_onboarded()
        if not self._is_onboarded_status(refreshed.get("onboarding_status")):
            status_display = refreshed.get("onboarding_status", "Unknown")
            message = f"Compute onboarding did not complete (status={status_display})."
            self.append_log("submit_data", message)
            raise RuntimeError(message)

        self.append_log("submit_data", "Compute onboarding completed successfully.")
        return refreshed

    def ensure_pre_onboarding(self) -> Dict[str, Any]:
        """
        Public wrapper to guarantee compute resources are onboarded and return
        the latest snapshot used when preparing join payloads.
        """
        return self._ensure_pre_onboarding()

    def _log_resource_snapshot(self, info: Dict[str, Any]) -> None:
        if not isinstance(info, dict):
            return

        summary: Dict[str, Any] = {}
        for key in ("onboarding_status", "onboarded_resources", "free_resources", "allocated_resources"):
            value = info.get(key)
            if value is None:
                continue
            if isinstance(value, str):
                summary[key] = _ANSI_RE.sub("", value)
            else:
                summary[key] = value

        dms_resources = info.get("dms_resources")
        if isinstance(dms_resources, dict):
            slim: Dict[str, Any] = {}
            for hw_key in ("cpu", "ram", "disk", "gpus"):
                if hw_key in dms_resources:
                    slim[hw_key] = dms_resources[hw_key]
            if slim:
                summary["dms_resources"] = slim

        if not summary:
            return

        parts = []
        status = summary.get("onboarding_status")
        if status is not None:
            parts.append(f"status={status}")
        onboarded = summary.get("onboarded_resources")
        if onboarded:
            parts.append(f"onboarded={onboarded}")
        if parts:
            self.append_log("submit_data", f"Hardware snapshot for submission: {' | '.join(parts)}")

        meta = {"timestamp": _timestamp(), "summary": summary}
        self.update_state(last_submit_payload_meta=meta)

    def api_submit_join(self, data: Dict[str, Any], resource_info: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Submit onboarding data to the selected organisation."""
        if self.use_mock_api:
            mock = {"status": "success", "request_id": "mock-request", "status_token": "mock-token"}
            self.append_log("submit_data", "Mock onboarding submit invoked.")
            return mock

        payload = dict(data or {})
        info: Dict[str, Any]
        try:
            info = dict(resource_info or {})
        except Exception:
            info = {}
        if not info:
            info = self._ensure_pre_onboarding()

        onboarding_status_raw = info.get("onboarding_status")
        onboarded = self._is_onboarded_status(onboarding_status_raw)
        onboarding_status_display = _ANSI_RE.sub("", str(onboarding_status_raw or "Unknown"))
        onboarded_resources = _ANSI_RE.sub("", str(info.get("onboarded_resources", "Unknown")))

        payload["resources"] = {
            "onboarding_status": onboarded,
            "onboarded_resources": onboarded_resources,
        }
        base_dms_resources = info.get("dms_resources")
        if isinstance(base_dms_resources, dict):
            dms_resources = dict(base_dms_resources)
        else:
            dms_resources = {}

        if "onboarded_resources" not in dms_resources:
            dms_resources["onboarded_resources"] = onboarded_resources
        dms_resources.setdefault("onboarding_status", onboarding_status_display)
        # Preserve plain-string aggregates for consumers that only expect text blobs.
        if "free_resources" not in dms_resources and info.get("free_resources") is not None:
            dms_resources["free_resources"] = info.get("free_resources")
        if "allocated_resources" not in dms_resources and info.get("allocated_resources") is not None:
            dms_resources["allocated_resources"] = info.get("allocated_resources")

        payload["dms_resources"] = dms_resources
        self._log_resource_snapshot(info)

        api_url = self.get_onboarding_api_url()
        if not api_url:
            raise RuntimeError("No onboarding API URL configured for the selected organisation.")

        endpoint = f"{api_url.rstrip('/')}/onboarding/submit/"
        self.append_log("submit_data", f"Submitting onboarding payload to {endpoint}")

        resp = self.session.post(endpoint, json=payload, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def api_check_status(self, request_id: str, status_token: str) -> Dict[str, Any]:
        """Poll the upstream onboarding API for status updates."""
        if self.use_mock_api:
            return {"status": "ready", "payload": {"message": "mock"}}

        api_url = self.get_onboarding_api_url()
        if not api_url:
            raise RuntimeError("No onboarding API URL configured for the selected organisation.")

        endpoint = f"{api_url.rstrip('/')}/onboarding/status/{request_id}/"
        resp = self.session.get(endpoint, params={"status_token": status_token}, timeout=15)
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------ #
    # Contract-enabled flow API methods
    # ------------------------------------------------------------------ #

    def api_confirm_caps(self, request_id: str, status_token: str, cap_type: str) -> Dict[str, Any]:
        """
        Notify Organization Manager that capabilities have been applied.
        
        Args:
            request_id: The onboarding request ID
            status_token: The status token for authentication
            cap_type: Either "contract" or "deployment"
            
        Returns:
            Response from Organization Manager API
        """
        log_step = "contract_caps_applied" if cap_type == "contract" else "deployment_caps_applied"
        
        if self.use_mock_api:
            self.append_log(log_step, f"Mock confirm-caps invoked for {cap_type} capabilities.")
            return {"status": "success"}
        
        api_url = self.get_onboarding_api_url()
        if not api_url:
            raise RuntimeError("No onboarding API URL configured for the selected organisation.")
        
        endpoint = f"{api_url.rstrip('/')}/onboarding/confirm-caps/{request_id}/"
        params = {"status_token": status_token, "cap_type": cap_type}
        
        self.append_log(log_step, f"Confirming {cap_type} capabilities to {endpoint}")
        
        resp = self.session.post(endpoint, params=params, timeout=15)
        resp.raise_for_status()
        return resp.json()

    def api_contract_received(self, request_id: str, status_token: str) -> Dict[str, Any]:
        """
        Notify Organization Manager that a contract has been received.
        
        Args:
            request_id: The onboarding request ID
            status_token: The status token for authentication
            
        Returns:
            Response from Organization Manager API
        """
        if self.use_mock_api:
            self.append_log("contract_received", "Mock contract-received invoked.")
            return {"status": "success"}
        
        api_url = self.get_onboarding_api_url()
        if not api_url:
            raise RuntimeError("No onboarding API URL configured for the selected organisation.")
        
        endpoint = f"{api_url.rstrip('/')}/onboarding/contract-received/{request_id}/"
        params = {"status_token": status_token}
        
        self.append_log("contract_received", f"Notifying contract received to {endpoint}")
        
        resp = self.session.post(endpoint, params=params, timeout=15)
        resp.raise_for_status()
        return resp.json()

    def api_contract_signed(self, request_id: str, status_token: str) -> Dict[str, Any]:
        """
        Notify Organization Manager that a contract has been signed.
        
        Args:
            request_id: The onboarding request ID
            status_token: The status token for authentication
            
        Returns:
            Response from Organization Manager API
        """
        if self.use_mock_api:
            self.append_log("contract_signed", "Mock contract-signed invoked.")
            return {"status": "success"}
        
        api_url = self.get_onboarding_api_url()
        if not api_url:
            raise RuntimeError("No onboarding API URL configured for the selected organisation.")
        
        endpoint = f"{api_url.rstrip('/')}/onboarding/contract-signed/{request_id}/"
        params = {"status_token": status_token}
        
        self.append_log("contract_signed", f"Notifying contract signed to {endpoint}")
        
        resp = self.session.post(endpoint, params=params, timeout=15)
        resp.raise_for_status()
        return resp.json()

    def poll_for_contracts(self, request_id: str, expected_contract_did: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Poll DMS for incoming contracts.

        When expected_contract_did is set (from the org manager API after the orchestrator
        creates a contract), we only treat the contract as "received" when the DMS list
        contains a contract with that contract_did, so we confirm receipt of the specific
        contract the orchestrator created.

        Args:
            request_id: The onboarding request ID (for logging)
            expected_contract_did: If set, only return a contract that matches this DID.

        Returns:
            Contract data if found (and matching expected_contract_did when provided), None otherwise
        """
        try:
            from .dms_utils import run_dms_command_with_passphrase
            
            # Execute: nunet actor cmd /dms/tokenomics/contract/list
            result = run_dms_command_with_passphrase(
                ["nunet", "actor", "cmd", "-c", "dms", "/dms/tokenomics/contract/list"],
                capture_output=True,
                text=True,
                check=False,
                timeout=60
            )
            
            if result.returncode != 0:
                logger.debug("Contract list command failed: %s", result.stderr or result.stdout)
                return None

            # Use full stdout for parsing (DMS command logging may truncate for logs only).
            output = (result.stdout or "").strip()
            if not output:
                return None
            
            try:
                data = json.loads(output)
                # DMS returns {"contracts": [...]}; fallback to raw array
                if isinstance(data, dict) and "contracts" in data:
                    contracts = data["contracts"] if isinstance(data["contracts"], list) else []
                elif isinstance(data, list):
                    contracts = data
                else:
                    contracts = [data] if data else []
            except json.JSONDecodeError:
                logger.warning("Failed to parse contract list response: %s", output[:200] if output else "")
                return None

            def _contract_did(c: dict) -> str:
                return (c.get("contract_did") or c.get("did") or "").strip()

            expected_did = (expected_contract_did or "").strip()

            # If we have an expected contract_did from the API (orchestrator-created), look for that specific contract
            if expected_did:
                for contract in contracts:
                    if not isinstance(contract, dict):
                        continue
                    if _contract_did(contract) != expected_did:
                        continue
                    # Found the contract the orchestrator created
                    seen_contracts = set(self.state.get("seen_contract_dids", []))
                    if expected_did not in seen_contracts:
                        self.update_state(seen_contract_dids=list(seen_contracts | {expected_did}))
                    self.append_log("contract_received", f"Contract received: {expected_did}")
                    return contract
                # Expected contract not in DMS list yet (or DID mismatch)
                list_dids = [_contract_did(c) for c in contracts if isinstance(c, dict)]
                logger.info(
                    "Expected contract_did %s not in DMS list (%d contracts: %s)",
                    expected_did[:50] + "..." if len(expected_did) > 50 else expected_did,
                    len(contracts),
                    list_dids[:5] if len(list_dids) > 5 else list_dids,
                )
                return None

            # No expected_contract_did: treat any new (unseen) contract as received (legacy behavior)
            seen_contracts = set(self.state.get("seen_contract_dids", []))
            new_contracts = [
                contract for contract in contracts
                if isinstance(contract, dict) and _contract_did(contract) and _contract_did(contract) not in seen_contracts
            ]

            if new_contracts:
                all_dids = seen_contracts | {_contract_did(c) for c in new_contracts}
                self.update_state(seen_contract_dids=list(all_dids))
                contract = new_contracts[0]
                self.append_log("contract_received", f"Contract detected: {_contract_did(contract) or 'unknown'}")
                return contract

            return None
            
        except Exception as exc:
            logger.error("Contract polling failed: %s", exc)
            self.append_log("contract_received", f"Contract polling error: {exc}")
            return None

    def sign_contract(self, contract_did: str) -> bool:
        """
        Sign a contract using nunet CLI.
        
        Args:
            contract_did: The DID of the contract to sign
            
        Returns:
            True if successful, False otherwise
        """
        try:
            self.append_log("contract_signed", f"Signing contract: {contract_did}")
            
            # Execute: nunet actor cmd /dms/tokenomics/contract/approve_local --contract-did <did>
            result = run_dms_command_with_passphrase(
                [
                    "nunet", "actor", "cmd", "-c", "dms",
                    "/dms/tokenomics/contract/approve_local",
                    "--contract-did", contract_did
                ],
                capture_output=True,
                text=True,
                check=False,
                timeout=30
            )
            
            if result.returncode != 0:
                error_msg = result.stderr or result.stdout or "Unknown error"
                logger.error("Contract signing failed: %s", error_msg)
                self.append_log("contract_signed", f"Contract signing failed: {error_msg}")
                return False
            
            output = (result.stdout or "").strip()
            self.append_log("contract_signed", f"Contract signed successfully. Output: {output}")
            return True
            
        except Exception as exc:
            logger.error("Failed to sign contract: %s", exc)
            self.append_log("contract_signed", f"Contract signing error: {exc}")
            return False

    def apply_contract_capabilities(self, contract_caps: str) -> bool:
        """
        Apply contract capabilities (require token from known orgs + provide token from org manager) and restart DMS service.
        
        Args:
            contract_caps: The provide capability token for contract interaction from Organization Manager
            
        Returns:
            True if successful, False otherwise
        """
        try:
            self.append_log("contract_caps_applied", "Applying contract capabilities...")
            
            # Get organization DID and role
            org_data = self.state.get("org_data") or {}
            org_did = org_data.get("did") if isinstance(org_data, dict) else None
            if not org_did:
                raise RuntimeError("No organization DID available")
            
            role_id = self.get_selected_role_id()
            
            # Generate and apply require token from known orgs file (contract caps only)
            require_success = False
            try:
                self.append_log("contract_caps_applied", "Generating contract require token from known orgs file...")
                require_success = self.generate_and_apply_require_token(
                    org_did, 
                    role_id=role_id,
                    template_key="contract_require_template",
                    log_step="contract_caps_applied"
                )
                if require_success:
                    self.append_log("contract_caps_applied", "Contract require token generated and anchored successfully.")
            except Exception as exc:
                logger.warning("Contract require token generation failed: %s", exc)
                self.append_log("contract_caps_applied", f"Contract require token generation failed: {exc}")
                # Continue anyway - provide token might be sufficient
            
            # Anchor the provide token (from Organization Manager)
            self.append_log("contract_caps_applied", "Anchoring contract provide token...")
            self._apply_provide_token(contract_caps)
            self.append_log("contract_caps_applied", "Contract provide token anchored successfully.")
            
            # Copy tokens to DMS user
            self.copy_capability_tokens_to_dms_user()
            
            # Restart DMS service
            self.append_log("contract_caps_applied", "Restarting nunet DMS service...")
            restart_success = self.restart_dms_service()
            
            if restart_success:
                self.append_log("contract_caps_applied", "DMS service restarted successfully.")
                return True
            else:
                self.append_log("contract_caps_applied", "DMS service restart failed.")
                return False
                
        except Exception as exc:
            logger.error("Failed to apply contract capabilities: %s", exc)
            self.append_log("contract_caps_applied", f"Failed to apply contract capabilities: {exc}")
            return False

    def apply_deployment_capabilities(
        self,
        deployment_caps: str,
        certificates: Optional[Dict[str, str]] = None,
        api_key: Optional[str] = None
    ) -> bool:
        """
        Apply deployment capabilities, certificates, and API key.
        
        Args:
            deployment_caps: The provide capability token from Organization Manager
            certificates: Dictionary with client_crt, client_key, infra_bundle_crt
            api_key: Elasticsearch API key
            
        Returns:
            True if successful, False otherwise
        """
        try:
            self.append_log("deployment_caps_applied", "Applying deployment capabilities...")
            
            # Get organization DID
            org_data = self.state.get("org_data") or {}
            org_did = org_data.get("did") if isinstance(org_data, dict) else None
            if not org_did:
                raise RuntimeError("No organization DID available")
            
            role_id = self.get_selected_role_id()
            
            # Generate and apply require token (from known orgs - deployment caps only)
            require_success = False
            try:
                require_success = self.generate_and_apply_require_token(
                    org_did, 
                    role_id=role_id,
                    template_key="deployment_require_template",
                    log_step="deployment_caps_applied"
                )
                if require_success:
                    self.append_log("deployment_caps_applied", "Deployment require token generated and anchored.")
            except Exception as exc:
                logger.warning("Deployment require token generation failed: %s", exc)
                self.append_log("deployment_caps_applied", f"Deployment require token generation failed: {exc}")
            
            # Apply provide token (from Organization Manager)
            if deployment_caps:
                self.append_log("deployment_caps_applied", "Anchoring deployment provide token...")
                self._apply_provide_token(deployment_caps)
            
            # Write certificates
            if certificates:
                self.append_log("deployment_caps_applied", "Writing mTLS certificates...")
                self._write_certificates(certificates)
            
            # Configure observability (API key)
            if api_key:
                payload_with_api_key = {"elasticsearch_api_key": api_key, "elastic_api_key": api_key}
                self.append_log("deployment_caps_applied", "Configuring observability (Elastic API key)...")
                self._configure_observability(payload_with_api_key)
            
            # Copy capability tokens to DMS user
            self.copy_capability_tokens_to_dms_user()
            
            # Restart DMS service
            self.append_log("deployment_caps_applied", "Restarting nunet DMS service...")
            restart_success = self.restart_dms_service()
            
            if restart_success:
                self.append_log("deployment_caps_applied", "Deployment capabilities applied and DMS restarted successfully.")
                return True
            else:
                self.append_log("deployment_caps_applied", "DMS service restart failed.")
                return False
                
        except Exception as exc:
            logger.error("Failed to apply deployment capabilities: %s", exc)
            self.append_log("deployment_caps_applied", f"Failed to apply deployment capabilities: {exc}")
            return False

    # ------------------------------------------------------------------ #
    # Capability and credential handling
    # ------------------------------------------------------------------ #

    def generate_and_apply_require_token(
        self,
        org_did: str,
        *,
        expiry_days: int = 30,
        role_id: Optional[str] = None,
        template_key: str = "require_template",
        log_step: str = "capabilities_applied",
    ) -> bool:
        """Generate a require token for *org_did* using the active role profile.
        
        Args:
            org_did: The organization DID to generate the token for
            expiry_days: Number of days until token expires (default 30)
            role_id: Role ID to use (defaults to selected role)
            template_key: Which template to use from the role profile. Options:
                - "require_template" (legacy, includes all caps)
                - "contract_require_template" (contract caps only)
                - "deployment_require_template" (deployment caps only)
            log_step: Step name to use for logging (default "capabilities_applied")
        """
        role_id = role_id or self.get_selected_role_id()
        profiles = self.get_role_profiles()
        profile = profiles.get(role_id) if role_id else {}
        require_template: Dict[str, Any] = {}
        if isinstance(profile, dict):
            # Try the requested template_key first, fall back to require_template for backwards compatibility
            require_template = profile.get(template_key) or profile.get("require_template") or {}

        topics = self._extract_topics(require_template)
        if role_id and (not require_template or not topics):
            reason = "template missing" if not require_template else "topics missing"
            logger.info(
                "Role profile for org=%s role=%s template_key=%s has %s; reloading from known organizations.",
                org_did,
                role_id,
                template_key,
                reason,
            )
            refreshed_profile = self._load_role_profile_from_known(org_did, role_id)
            if refreshed_profile:
                profile = refreshed_profile
                # Try the requested template_key first, fall back to require_template
                require_template = profile.get(template_key) or profile.get("require_template") or {}
                topics = self._extract_topics(require_template)
                if isinstance(profiles, dict):
                    profiles[role_id] = profile

        context = require_template.get("context")
        if not isinstance(context, str) or not context.strip():
            context = "dms"
        else:
            context = context.strip()

        caps = self._extract_caps(require_template)
        if not caps:
            label = (profile or {}).get("label") if isinstance(profile, dict) else None
            role_label = label or role_id or "active role"
            raise RuntimeError(f"Role '{role_label}' is missing {template_key}.caps; cannot generate require token.")

        source_path = self._active_known_orgs_path()
        logger.info(
            "Known orgs path for org=%s role=%s resolved to %s",
            org_did,
            role_id or "<default>",
            source_path or "<not found>",
        )
        logger.debug(
            "Role %s for org=%s role=%s -> %s",
            template_key,
            org_did,
            role_id or "<default>",
            require_template,
        )
        topic_log_target = topics if topics else ["<none>"]
        logger.info(
            "Preparing require token org=%s role=%s template=%s caps=%s topics=%s",
            org_did,
            role_id or "<default>",
            template_key,
            caps,
            topic_log_target,
        )
        if topics:
            self.append_log(
                log_step,
                f"Require token topics for role '{role_id or 'default'}': {', '.join(topics)}",
            )
        else:
            self.append_log(
                log_step,
                f"No topics configured for role '{role_id or 'default'}'; continuing without --topic flags.",
            )

        expiry = (datetime.utcnow() + timedelta(days=expiry_days)).strftime("%Y-%m-%dT%H:%M:%SZ")
        if role_id:
            self.append_log(log_step, f"Generating require token for role '{role_id}' (expires {expiry})")
        else:
            self.append_log(log_step, f"Generating require token with default profile (expires {expiry})")

        cmd = [
            "nunet",
            "cap",
            "grant",
            "--context",
            context,
        ]
        for cap in caps:
            cmd.extend(["--cap", cap])
        for topic in topics:
            cmd.extend(["--topic", topic])
        cmd.extend(["--expiry", expiry, org_did])

        result = run_dms_command_with_passphrase(
            cmd,
            capture_output=True,
            text=True,
            check=True,
        )

        token = (result.stdout or "").strip()
        if not token:
            raise RuntimeError("Require token generation produced no output.")

        self.append_log(log_step, "Anchoring require token...")
        run_dms_command_with_passphrase(
            ["nunet", "cap", "anchor", "-c", context, "--require", token],
            capture_output=True,
            text=True,
            check=True,
        )
        return True

    def _apply_provide_token(self, provide_token: str) -> None:
        run_dms_command_with_passphrase(
            ["nunet", "cap", "anchor", "-c", "dms", "--provide", provide_token],
            capture_output=True,
            text=True,
            check=True,
        )

    def _configure_observability(self, payload: Dict[str, Any]) -> None:
        api_key = payload.get("elasticsearch_api_key") or payload.get("elastic_api_key")
        if not api_key:
            return

        # Ensure we use the absolute path to the config file
        config_path = NUNET_CONFIG_PATH.resolve()
        updates = [
            ("observability.elasticsearch_api_key", api_key),
            ("observability.elasticsearch_enabled", "true"),
            ("observability.elasticsearch_url", payload.get("elasticsearch_url", "https://telemetry.nunet.io")),
            ("observability.elasticsearch_index", "nunet-dms"),
            ("observability.elastic.flush_interval", 5),
            ("observability.elastic.insecure_skip_verify", "true"),
            ("observability.elastic.api_key", api_key),
            ("observability.elastic.enabled", "true"),
            ("observability.elastic.url", payload.get("elasticsearch_url", "https://telemetry.nunet.io")),
            ("observability.elastic.index", "nunet-dms"),
            ("observability.elastic.flush_interval", 5),
            ("observability.elastic.insecure_skip_verify", "true"),
            ("observability.logging.level", "DEBUG"),
            ("observability.logging.file", "/home/nunet/logs/nunet-dms.log"),
            ("observability.logging.rotation.max_age_days", 28),
            ("observability.logging.rotation.max_size_mb", 100),
            ("observability.logging.rotation.max_backups", 3),
        ]

        for key, value in updates:
            try:
                # Run nunet config set as nunet user to preserve file ownership and permissions
                # Explicitly specify the config file path with --config flag
                subprocess.run(
                    ["sudo", "-u", "nunet", "nunet", "--config", str(config_path), "config", "set", key, str(value)],
                    capture_output=True,
                    text=True,
                    check=True,
                )
            except subprocess.CalledProcessError as exc:  # pragma: no cover - system specific
                logger.warning("Failed updating %s via nunet config: %s", key, exc.stderr or exc.stdout or exc)
                self.append_log("capabilities_applied", f"Failed updating {key}: {exc}")
                break

    def _write_certificates(self, payload: Dict[str, Any]) -> None:
        cert_dir = self._STATE_DIR / "ddns-client" / "certs" / "certs"
        cert_dir.mkdir(parents=True, exist_ok=True)

        mapping = {
            "client.crt": payload.get("client_crt"),
            "client.key": payload.get("client_key"),
            "infra-bundle-ca.crt": payload.get("infra_bundle_crt"),
        }

        written = []
        for name, content in mapping.items():
            if not content:
                continue
            path = cert_dir / name
            path.write_text(content)
            if name.endswith(".key"):
                os.chmod(path, 0o600)
            written.append(name)

        if written:
            self.append_log("mtls_certs_saved", f"Wrote certificates: {', '.join(written)}")

        missing = [name for name, content in mapping.items() if not content]
        if missing:
            self.append_log("mtls_certs_saved", f"Missing certificates in payload: {', '.join(missing)}")

    def copy_capability_tokens_to_dms_user(self) -> bool:
        """Copy ubuntu user's capability tokens into the nunet service account."""
        src = DMS_CAP_FILE
        dest = SERVICE_DMS_CAP_FILE

        if not src.exists():
            self.append_log("capability_token_copy", f"Source capability file not found: {src}")
            return False

        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            subprocess.run(["sudo", "cp", str(src), str(dest)], capture_output=True, text=True, check=True)
            subprocess.run(["sudo", "chown", "nunet:nunet", str(dest)], capture_output=True, text=True, check=True)
            subprocess.run(["sudo", "chmod", "640", str(dest)], capture_output=True, text=True, check=True)
            self.append_log("capability_token_copy", "Capability tokens copied to nunet service user.")
            return True
        except subprocess.CalledProcessError as exc:  # pragma: no cover - depends on sudo policy
            logger.warning("Failed copying capability tokens: %s", exc.stderr or exc.stdout or exc)
            self.append_log("capability_token_copy", f"Failed copying capability tokens: {exc}")
            return False

    # ------------------------------------------------------------------ #
    # Post-approval pipeline
    # ------------------------------------------------------------------ #

    def process_post_approval_payload(self, payload: Dict[str, Any]) -> bool:
        """
        Apply capability updates, write credentials, and refresh local services
        once the onboarding request has been approved.
        """
        try:
            role_id = self.get_selected_role_id()
            org_did = payload.get("organization_did")
            if not org_did:
                org_data = self.state.get("org_data") or {}
                if isinstance(org_data, dict):
                    org_did = org_data.get("did")

            form_wallet = (self.state.get("form_data") or {}).get("wallet_address")
            if form_wallet:
                self.append_log("join_data_received", f"Wallet on record: {form_wallet}")

            require_success = False
            if org_did:
                try:
                    require_success = self.generate_and_apply_require_token(org_did, role_id=role_id)
                except Exception as exc:
                    logger.warning("Require token generation failed: %s", exc)
                    self.append_log("capabilities_applied", f"Require token generation failed: {exc}")

            provide_token = payload.get("capability_token") or payload.get("provide_token")
            if provide_token:
                self.append_log("capabilities_applied", "Anchoring provide token...")
                self._apply_provide_token(provide_token)

            if org_did:
                try:
                    from backend.nunet_api import role_metadata

                    role_metadata.record_role_tokens(
                        org_did,
                        provide_token=provide_token,
                        require_generated=require_success,
                    )
                except Exception as exc:
                    logger.debug("Failed to update role metadata cache: %s", exc)

            self._configure_observability(payload)
            self._write_certificates(payload)
            # Enable Caddy proxy if certificates are available
            try:
                client_crt = payload.get("client_crt")
                client_key = payload.get("client_key")
                ca_bundle = payload.get("infra_bundle_crt")
                if client_crt and client_key and ca_bundle:
                    self.append_log("mtls_certs_saved", "All required certificates available. Enabling Caddy proxy service...")
                    # Service is now installed via nunet-appliance-web deb package
                    # No manual installation needed
                    status = self.caddy_proxy_manager.get_caddy_proxy_status()
                    self.append_log("mtls_certs_saved", f"Caddy proxy service status: {status}")
                else:
                    self.append_log("mtls_certs_saved", "Not all certificates available. Skipping Caddy proxy enablement.")
            except Exception as exc:
                self.append_log("mtls_certs_saved", f"Error enabling Caddy proxy service: {exc}")
            self.copy_capability_tokens_to_dms_user()

            result = self.dms_manager.onboard_compute()
            if result.get("status") != "success":
                raise RuntimeError(result.get("message", "Compute onboarding failed"))
            self.append_log("capabilities_onboarded", "Compute onboarding completed after approval.")

            self.update_state(processing=False, processed_ok=True)
            return True
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("Post approval processing failed: %s", exc)
            self.update_state(error=str(exc), processing=False, processed_ok=False)
            return False

    def leave_organization(self, org_did: str) -> Dict[str, int]:
        """
        Remove anchored capability tokens for *org_did* and clear local metadata.
        """
        org_did = (org_did or "").strip()
        if not org_did:
            raise ValueError("Organization DID is required.")

        provide_tokens, require_tokens = get_tokens_for_org(org_did)
        removed_provide = 0
        removed_require = 0

        for token in provide_tokens:
            try:
                run_dms_command_with_passphrase(
                    [
                        "nunet",
                        "-c",
                        "dms",
                        "cap",
                        "remove",
                        "--provide",
                        json.dumps(token, separators=(",", ":")),
                    ],
                    capture_output=True,
                    text=True,
                    check=True,
                )
                removed_provide += 1
            except subprocess.CalledProcessError as exc:
                logger.warning(
                    "Failed to remove provide token for %s: %s",
                    org_did,
                    exc.stderr or exc.stdout or exc,
                )

        for token in require_tokens:
            try:
                run_dms_command_with_passphrase(
                    [
                        "nunet",
                        "-c",
                        "dms",
                        "cap",
                        "remove",
                        "--require",
                        json.dumps(token, separators=(",", ":")),
                    ],
                    capture_output=True,
                    text=True,
                    check=True,
                )
                removed_require += 1
            except subprocess.CalledProcessError as exc:
                logger.warning(
                    "Failed to remove require token for %s: %s",
                    org_did,
                    exc.stderr or exc.stdout or exc,
                )

        try:
            from backend.nunet_api import role_metadata

            role_metadata.remove_org(org_did)
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug("Unable to clear role metadata for %s: %s", org_did, exc)

        org_data = self.state.get("org_data") or {}
        if isinstance(org_data, dict) and org_data.get("did") == org_did:
            self.update_state(
                org_data=None,
                form_data={},
                request_id=None,
                status_token=None,
                api_status=None,
                api_payload=None,
                processing=False,
                processed_ok=False,
                error=None,
            )
        else:
            # still persist metadata removal
            self._write_state()

        self.copy_capability_tokens_to_dms_user()
        self.append_log("leave_org", f"Removed {removed_provide} provide and {removed_require} require tokens for {org_did}")
        return {"provide": removed_provide, "require": removed_require}

    # ------------------------------------------------------------------ #
    # Service management
    # ------------------------------------------------------------------ #

    def restart_dms_service(self) -> bool:
        """Restart the nunetdms service and report whether it returned to active."""
        try:
            subprocess.run(
                ["sudo", "systemctl", "restart", "nunetdms"],
                capture_output=True,
                text=True,
                check=True,
            )
            time.sleep(2)
            status = subprocess.run(
                ["sudo", "systemctl", "is-active", "nunetdms"],
                capture_output=True,
                text=True,
                check=False,
            )
            active = (status.stdout or "").strip() == "active"
            detail = (status.stdout or status.stderr or "").strip()
            if active:
                self.append_log("dms_restart", "DMS service restarted successfully.")
            else:
                self.append_log("dms_restart", f"DMS service restart returned status: {detail or 'unknown'}")
            return active
        except subprocess.CalledProcessError as exc:  # pragma: no cover - depends on sudo policy
            logger.error("Failed to restart DMS service: %s", exc)
            self.append_log("dms_restart", f"DMS service restart failed: {exc}")
            return False

    def mark_onboarding_complete(self, org_name: Optional[str] = None) -> bool:
        """Mark the onboarding flow as complete (used by FastAPI after manual steps)."""
        if org_name:
            org_data = self.state.setdefault("org_data", {}) or {}
            if isinstance(org_data, dict):
                org_data["name"] = org_name
        self.update_state(step="complete", completed=True, processing=False, processed_ok=True)
        return True
