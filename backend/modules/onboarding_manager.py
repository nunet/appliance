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
    ONBOARDING_LOG_FILE,
    ONBOARDING_STATE_FILE,
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
        }

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
        status_raw = str(info.get("onboarding_status", ""))
        if "ONBOARDED" in status_raw.upper():
            return info

        self.append_log("submit_data", "Running onboard-max.sh to refresh compute resources...")
        result = self.dms_manager.onboard_compute()
        if result.get("status") != "success":
            message = result.get("message", "Compute onboarding failed")
            raise RuntimeError(message)
        self.append_log("submit_data", "Compute onboarding completed successfully.")
        return get_dms_resource_info()

    def api_submit_join(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Submit onboarding data to the selected organisation."""
        if self.use_mock_api:
            mock = {"status": "success", "request_id": "mock-request", "status_token": "mock-token"}
            self.append_log("submit_data", "Mock onboarding submit invoked.")
            return mock

        payload = dict(data or {})
        resource_info = self._ensure_pre_onboarding()

        onboarding_status_raw = str(resource_info.get("onboarding_status", ""))
        onboarded = "ONBOARDED" in onboarding_status_raw.upper()
        onboarded_resources = _ANSI_RE.sub("", str(resource_info.get("onboarded_resources", "Unknown")))

        payload.setdefault(
            "resources",
            {
                "onboarding_status": onboarded,
                "onboarded_resources": onboarded_resources,
            },
        )
        payload.setdefault("dms_resources", resource_info.get("dms_resources", {}))

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
    # Capability and credential handling
    # ------------------------------------------------------------------ #

    def generate_and_apply_require_token(
        self,
        org_did: str,
        *,
        expiry_days: int = 30,
        role_id: Optional[str] = None,
    ) -> bool:
        """Generate a require token for *org_did* using the active role profile."""
        role_id = role_id or self.get_selected_role_id()
        profiles = self.get_role_profiles()
        profile = profiles.get(role_id) if role_id else {}
        require_template = {}
        if isinstance(profile, dict):
            require_template = profile.get("require_template") or {}

        context = require_template.get("context")
        if not isinstance(context, str) or not context.strip():
            context = "dms"
        else:
            context = context.strip()

        caps = self._extract_caps(require_template)
        if not caps:
            label = (profile or {}).get("label") if isinstance(profile, dict) else None
            role_label = label or role_id or "active role"
            raise RuntimeError(f"Role '{role_label}' is missing require_template.caps; cannot generate require token.")

        topics_raw = require_template.get("topics") if isinstance(require_template, dict) else None
        topics: List[str] = []
        if isinstance(topics_raw, list):
            for topic in topics_raw:
                if not isinstance(topic, str):
                    continue
                clean_topic = topic.strip()
                if clean_topic and clean_topic not in topics:
                    topics.append(clean_topic)

        expiry = (datetime.utcnow() + timedelta(days=expiry_days)).strftime("%Y-%m-%dT%H:%M:%SZ")
        if role_id:
            self.append_log("capabilities_applied", f"Generating require token for role '{role_id}' (expires {expiry})")
        else:
            self.append_log("capabilities_applied", f"Generating require token with default profile (expires {expiry})")

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

        self.append_log("capabilities_applied", "Anchoring require token...")
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

        config_path = Path("/home/nunet/config/dms_config.json")
        updates = [
            ("observability.elasticsearch_api_key", api_key),
            ("observability.elasticsearch_enabled", "true"),
            ("observability.elasticsearch_url", payload.get("elasticsearch_url", "https://telemetry.nunet.io")),
        ]

        for key, value in updates:
            try:
                subprocess.run(
                    ["nunet", "--config", str(config_path), "config", "set", key, str(value)],
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
        src = Path("/home/ubuntu/.nunet/cap/dms.cap")
        dest = Path("/home/nunet/.nunet/cap/dms.cap")

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
                    self.caddy_proxy_manager.install_systemd_service(interval=30)
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
