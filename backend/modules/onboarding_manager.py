"""
Programmatic onboarding service for NuNet appliances.

This module keeps the public API that legacy scripts expect while modernising
logging, state management, and dependency handling.  Prefer importing
OnboardingService; OnboardingManager remains as a deprecated alias.
"""

from __future__ import annotations

import glob
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional

import requests

from .caddy_proxy_manager import CaddyProxyManager
from .ddns_manager import DDNSManager
from .dms_manager import DMSManager
from .logging_config import get_logger
from .org_utils import (
    get_joined_organizations_with_details,
    get_joined_organizations_with_names,
    load_known_organizations,
)
from modules.dms_utils import (
    get_dms_resource_info,
    get_dms_status_info,
    run_dms_command_with_passphrase,
)

logger = get_logger(__name__)

ONBOARDING_STATES = [
    "init",
    "select_org",
    "collect_join_data",
    "submit_data",
    "join_data_sent",
    "pending_authorization",
    "join_data_received",
    "capabilities_applied",
    "capabilities_onboarded",
    "telemetry_configured",
    "mtls_certs_saved",
    "complete",
    "rejected",
]


class OnboardingService:
    """Business logic helper for the organization onboarding flow."""

    STATE_PATH = Path.home() / "nunet" / "appliance" / "onboarding_state.json"
    LOG_PATH = Path.home() / "nunet" / "appliance" / "onboarding.log"
    SERVICE_NAME = "nunet-onboarding.service"

    def __init__(
        self,
        *,
        use_mock_api: bool = False,
        dms_manager: Optional[DMSManager] = None,
        org_manager: Optional[Any] = None,
        caddy_proxy_manager: Optional[CaddyProxyManager] = None,
        ddns_manager: Optional[DDNSManager] = None,
    ) -> None:
        self.dms_manager = dms_manager or DMSManager()
        from .organization_manager import OrganizationManager  # local import to avoid cycles

        self.org_manager = org_manager or OrganizationManager()
        self.caddy_proxy_manager = caddy_proxy_manager or CaddyProxyManager()
        self.ddns_manager = ddns_manager or DDNSManager()
        self.use_mock_api = use_mock_api
        self.state: Optional[Dict[str, Any]] = self.load_state()
        logger.debug(
            "OnboardingService initialised",
            extra={"state_path": str(self.STATE_PATH), "use_mock_api": use_mock_api},
        )

    @staticmethod
    def _initial_state() -> Dict[str, Any]:
        return {
            "step": "init",
            "progress": 0,
            "wormhole_code": None,
            "form_data": {},
            "error": None,
            "logs": [],
        }

    def _ensure_state_dict(self) -> Dict[str, Any]:
        if self.state is None:
            self.state = self._initial_state()
        return self.state

    def _ensure_state_file(self) -> None:
        path = self.STATE_PATH
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(self._initial_state(), indent=2), encoding="utf-8")
            logger.debug("Created default onboarding state file", extra={"path": str(path)})

    def load_state(self) -> Optional[Dict[str, Any]]:
        try:
            if self.STATE_PATH.exists():
                with self.STATE_PATH.open("r", encoding="utf-8") as handle:
                    return json.load(handle)
        except Exception as exc:
            logger.warning("Failed to load onboarding state", extra={"error": str(exc)})
        return None

    def save_state(self) -> None:
        try:
            self._ensure_state_file()
            with self.STATE_PATH.open("w", encoding="utf-8") as handle:
                json.dump(self._ensure_state_dict(), handle, indent=2)
        except Exception as exc:
            logger.error("Failed to persist onboarding state", extra={"error": str(exc)})

    def append_log(self, step: str, message: str, *, only_on_step_change: bool = False) -> None:
        state = self._ensure_state_dict()
        if only_on_step_change:
            logs = state.get("logs", [])
            if logs and logs[-1].get("step") == step:
                return
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        entry = {"timestamp": timestamp, "step": step, "message": message}
        state.setdefault("logs", []).append(entry)
        self.save_state()

    def update_state(self, **kwargs: Any) -> None:
        state = self._ensure_state_dict()
        step = kwargs.get("step")
        if step:
            self.append_log(step, f"Step changed to {step}", only_on_step_change=True)
        state.update(kwargs)
        self.save_state()

    def clear_state(self) -> None:
        if self.STATE_PATH.exists():
            try:
                self.STATE_PATH.unlink()
            except Exception as exc:
                logger.warning("Failed to clear onboarding state", extra={"error": str(exc)})
        self.state = self.load_state()
    def install_systemd_service(self) -> None:
        import sys

        python_exec = sys.executable
        script_path = Path(__file__).parent.parent / "scripts" / "onboarding_service.py"
        working_dir = script_path.parent
        service_content = f"""
[Unit]
Description=NuNet Onboarding Service
After=network.target loadubuntukeyring.service
Requires=loadubuntukeyring.service

[Service]
User=ubuntu
Group=ubuntu
KeyringMode=shared
Type=simple
Restart=on-failure
WorkingDirectory={working_dir}
ExecStart={python_exec} {script_path}

[Install]
WantedBy=multi-user.target
"""
        service_path = Path("/etc/systemd/system") / self.SERVICE_NAME
        try:
            with tempfile.NamedTemporaryFile("w", delete=False) as tf:
                tf.write(service_content)
                temp_path = Path(tf.name)
            subprocess.run(["sudo", "mv", str(temp_path), str(service_path)], check=True)
            subprocess.run(["sudo", "chown", "root:root", str(service_path)], check=True)
            subprocess.run(["sudo", "systemctl", "daemon-reload"], check=True)
            subprocess.run(["sudo", "systemctl", "enable", self.SERVICE_NAME], check=True)
            subprocess.run(["sudo", "systemctl", "restart", self.SERVICE_NAME], check=True)
            logger.info("Systemd onboarding service installed and started", extra={"service": self.SERVICE_NAME})
        except Exception as exc:
            logger.error("Failed to install onboarding systemd service", extra={"error": str(exc)})

    def enable_systemd_service(self) -> None:
        try:
            subprocess.run(["sudo", "systemctl", "enable", self.SERVICE_NAME], check=True)
            subprocess.run(["sudo", "systemctl", "start", self.SERVICE_NAME], check=True)
            logger.info("Enabled onboarding systemd service", extra={"service": self.SERVICE_NAME})
        except Exception as exc:
            logger.error("Failed to enable onboarding service", extra={"error": str(exc)})

    def stop_systemd_service(self) -> None:
        try:
            subprocess.run(["sudo", "systemctl", "stop", self.SERVICE_NAME], check=True)
            logger.info("Stopped onboarding systemd service", extra={"service": self.SERVICE_NAME})
        except Exception as exc:
            logger.error("Failed to stop onboarding service", extra={"error": str(exc)})

    def disable_systemd_service(self) -> None:
        try:
            subprocess.run(["sudo", "systemctl", "stop", self.SERVICE_NAME], check=True)
            subprocess.run(["sudo", "systemctl", "disable", self.SERVICE_NAME], check=True)
            logger.info("Disabled onboarding systemd service", extra={"service": self.SERVICE_NAME})
        except Exception as exc:
            logger.error("Failed to disable onboarding service", extra={"error": str(exc)})

    def uninstall_systemd_service(self) -> None:
        service_path = Path("/etc/systemd/system") / self.SERVICE_NAME
        try:
            subprocess.run(["sudo", "systemctl", "stop", self.SERVICE_NAME], check=True)
            subprocess.run(["sudo", "systemctl", "disable", self.SERVICE_NAME], check=True)
            if service_path.exists():
                subprocess.run(["sudo", "rm", str(service_path)], check=True)
            subprocess.run(["sudo", "systemctl", "daemon-reload"], check=True)
            logger.info("Uninstalled onboarding systemd service", extra={"service": self.SERVICE_NAME})
        except Exception as exc:
            logger.error("Failed to uninstall onboarding service", extra={"error": str(exc)})

    def get_onboarding_api_url(self) -> Optional[str]:
        state = self._ensure_state_dict()
        org_data = state.get("org_data") or {}
        org_did = org_data.get("did")
        if not org_did:
            logger.warning("Cannot resolve onboarding API URL without organization DID")
            return None
        known_orgs = load_known_organizations()
        entry = known_orgs.get(org_did) if isinstance(known_orgs, dict) else None
        if isinstance(entry, dict):
            api_url = entry.get("onboarding_api_url")
            logger.info("Resolved onboarding API URL", extra={"org_did": org_did, "api_url": api_url})
            return api_url
        logger.warning("No onboarding API URL found", extra={"org_did": org_did})
        return None

    def api_submit_join(self, data: Dict[str, Any]) -> Dict[str, Any]:
        if self.use_mock_api:
            return self.mock_api_submit_join(data)

        try:
            resource_info_pre = get_dms_resource_info()
            status_text = resource_info_pre.get("onboarding_status", "Unknown")
            already_onboarded = isinstance(status_text, str) and "ONBOARDED" in status_text
            if not already_onboarded:
                self.append_log("submit_data", "Running onboard-max.sh before submitting join request...")
                result = self.dms_manager.onboard_compute()
                if not result or result.get("status") != "success":
                    message = (result or {}).get("message") or "Unknown error"
                    self.append_log("submit_data", f"Pre-onboarding failed: {message}")
                    raise RuntimeError(f"Pre-onboarding failed: {message}")
                self.append_log("submit_data", "Pre-onboarding completed successfully")
        except Exception as exc:
            logger.exception("Pre-onboarding step failed", extra={"error": str(exc)})
            raise

        self.append_log("submit_data", "Collecting onboarded resource information...")
        try:
            resource_info = get_dms_resource_info()
            onboarding_status = resource_info.get("onboarding_status", "Unknown")
            onboarded_resources = resource_info.get("onboarded_resources", "Unknown")
            is_onboarded = "ONBOARDED" in str(onboarding_status)
            clean_resources = str(onboarded_resources).replace("\033[92m", "").replace("\033[0m", "").replace("\033[91m", "")
            data["dms_resources"] = resource_info.get("dms_resources", {})
            data["resources"] = {
                "onboarding_status": is_onboarded,
                "onboarded_resources": clean_resources,
            }
            logger.info(
                "Collected resource metadata for onboarding submission",
                extra={"onboarded": is_onboarded, "resources": clean_resources},
            )
        except Exception as exc:
            logger.warning("Failed to collect resource information", extra={"error": str(exc)})
            data["resources"] = {
                "onboarding_status": False,
                "onboarded_resources": "Unknown (collection failed)",
            }

        api_url = self.get_onboarding_api_url()
        if not api_url:
            raise RuntimeError("No onboarding_api_url configured for selected organization")

        try:
            payload = json.dumps(data)
            logger.info("Submitting onboarding data", extra={"api_url": api_url, "payload": payload})
            resp = requests.post(f"{api_url}/onboarding/submit/", json=data, timeout=30)
            logger.info("Onboarding submit response", extra={"status": resp.status_code, "body": resp.text})
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            logger.exception("onboarding submit failed", extra={"error": str(exc)})
            self.append_log("submit_data", f"API error: {exc}", only_on_step_change=True)
            raise

    def api_check_status(self, request_id: str, status_token: str) -> Dict[str, Any]:
        if self.use_mock_api:
            return self.mock_api_check_status(request_id)
        api_url = self.get_onboarding_api_url()
        if not api_url:
            raise RuntimeError("No onboarding_api_url configured for selected organization")
        try:
            logger.info(
                "Polling onboarding status",
                extra={"api_url": api_url, "request_id": request_id},
            )
            resp = requests.get(
                f"{api_url}/onboarding/status/{request_id}/",
                params={"status_token": status_token},
                timeout=10,
            )
            logger.info("Onboarding status response", extra={"status": resp.status_code, "body": resp.text})
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            logger.exception("onboarding status poll failed", extra={"error": str(exc)})
            self.append_log("join_data_sent", f"API status check error: {exc}", only_on_step_change=True)
            raise

    def _log_step(self, step: str, message: str, *, output: Optional[str] = None, error: Optional[str] = None) -> None:
        log_msg = message
        if output:
            log_msg += f"\nOutput: {output.strip()}"
        if error:
            log_msg += f"\nError: {error.strip()}"
        self.append_log(step, log_msg)
        logger.info("[%s] %s", step, log_msg)
    def generate_and_apply_require_token(self, org_did: str) -> bool:
        try:
            expiry_date = datetime.utcnow() + timedelta(days=30)
            grant_expiry = expiry_date.strftime("%Y-%m-%dT%H:%M:%SZ")
            self._log_step(
                "capabilities_applied",
                f"Generating require token with expiry {grant_expiry}",
            )
            result = run_dms_command_with_passphrase(
                [
                    "nunet",
                    "cap",
                    "grant",
                    "--context",
                    "dms",
                    "--cap",
                    "/dms/deployment",
                    "--cap",
                    "/dms/tokenomics/contract",
                    "--cap",
                    "/broadcast",
                    "--cap",
                    "/public",
                    "--topic",
                    "/nunet",
                    "--expiry",
                    grant_expiry,
                    org_did,
                ],
                capture_output=True,
                text=True,
                check=True,
            )
            require_token = (result.stdout or "").strip()
            self._log_step(
                "capabilities_applied",
                f"Generated require token: {require_token}",
                output=result.stdout,
            )
            anchor_result = run_dms_command_with_passphrase(
                ["nunet", "cap", "anchor", "-c", "dms", "--require", require_token],
                capture_output=True,
                text=True,
                check=True,
            )
            self._log_step(
                "capabilities_applied",
                "Require token applied successfully",
                output=anchor_result.stdout,
            )
            return True
        except subprocess.CalledProcessError as exc:
            self._log_step(
                "capabilities_applied",
                "Error generating or applying require token",
                output=exc.stdout,
                error=exc.stderr,
            )
            self.update_state(error=f"Error generating/applying require token: {exc.stderr}")
        except Exception as exc:
            self._log_step(
                "capabilities_applied",
                f"Exception generating/applying require token: {exc}",
            )
            self.update_state(error=str(exc))
        return False

    def process_post_approval_payload(self, payload: Dict[str, Any]) -> bool:
        try:
            org_did = payload.get("organization_did") or (
                (self.state or {}).get("org_data") or {}
            ).get("did")
            if org_did:
                self._log_step(
                    "capabilities_applied",
                    f"Generating and applying require token for {org_did}",
                )
                if not self.generate_and_apply_require_token(org_did):
                    return False
            else:
                self._log_step("capabilities_applied", "No organization DID available; skipping require token")
        except Exception as exc:
            self._log_step("capabilities_applied", f"Exception in require token generation: {exc}")
            self.update_state(error=str(exc))
            return False

        try:
            provide_token = payload.get("capability_token")
            if provide_token:
                self._log_step("capabilities_applied", "Applying provide token")
                result = run_dms_command_with_passphrase(
                    ["nunet", "cap", "anchor", "-c", "dms", "--provide", provide_token],
                    capture_output=True,
                    text=True,
                    check=True,
                )
                self._log_step(
                    "capabilities_applied",
                    "Provide token applied successfully",
                    output=result.stdout,
                )
            else:
                self._log_step("capabilities_applied", "No provide token present in payload")
        except subprocess.CalledProcessError as exc:
            self._log_step(
                "capabilities_applied",
                "Error applying provide token",
                output=exc.stdout,
                error=exc.stderr,
            )
            self.update_state(error=f"Error applying provide token: {exc.stderr}")
            return False
        except Exception as exc:
            self._log_step(
                "capabilities_applied",
                f"Exception applying provide token: {exc}",
            )
            self.update_state(error=str(exc))
            return False

        try:
            elastic_api_key = payload.get("elasticsearch_api_key") or payload.get("elastic_api_key")
            config_path = Path("/home/nunet/config/dms_config.json")
            if elastic_api_key:
                self._log_step("capabilities_applied", "Configuring Elasticsearch credentials")
                subprocess.run(
                    [
                        "nunet",
                        "--config",
                        str(config_path),
                        "config",
                        "set",
                        "observability.elasticsearch_api_key",
                        elastic_api_key,
                    ],
                    capture_output=True,
                    text=True,
                    check=True,
                )
                subprocess.run(
                    [
                        "nunet",
                        "--config",
                        str(config_path),
                        "config",
                        "set",
                        "observability.elasticsearch_enabled",
                        "true",
                    ],
                    capture_output=True,
                    text=True,
                    check=True,
                )
                subprocess.run(
                    [
                        "nunet",
                        "--config",
                        str(config_path),
                        "config",
                        "set",
                        "observability.elasticsearch_url",
                        "https://telemetry.nunet.io",
                    ],
                    capture_output=True,
                    text=True,
                    check=True,
                )
                self._log_step("capabilities_applied", "Elasticsearch configuration updated")
            else:
                self._log_step("capabilities_applied", "No Elasticsearch API key supplied; skipping")
        except subprocess.CalledProcessError as exc:
            self._log_step(
                "capabilities_applied",
                "Error configuring Elasticsearch",
                output=exc.stdout,
                error=exc.stderr,
            )
            self.update_state(error=f"Error setting Elasticsearch config: {exc.stderr}")
            return False
        except Exception as exc:
            self._log_step("capabilities_applied", f"Exception configuring Elasticsearch: {exc}")
            self.update_state(error=str(exc))
            return False

        try:
            cert_dir = Path.home() / "nunet" / "appliance" / "ddns-client" / "certs" / "certs"
            cert_dir.mkdir(parents=True, exist_ok=True)
            client_crt = payload.get("client_crt")
            client_key = payload.get("client_key")
            ca_bundle = payload.get("infra_bundle_crt")
            written = []
            if client_crt:
                (cert_dir / "client.crt").write_text(client_crt, encoding="utf-8")
                written.append("client.crt")
            if client_key:
                key_path = cert_dir / "client.key"
                key_path.write_text(client_key, encoding="utf-8")
                os.chmod(key_path, 0o600)
                written.append("client.key")
            if ca_bundle:
                (cert_dir / "infra-bundle-ca.crt").write_text(ca_bundle, encoding="utf-8")
                written.append("infra-bundle-ca.crt")
            self._log_step("mtls_certs_saved", f"Certificates written: {', '.join(written) if written else 'none'}")
            missing = [
                name
                for name, present in (
                    ("client.crt", client_crt),
                    ("client.key", client_key),
                    ("infra-bundle-ca.crt", ca_bundle),
                )
                if not present
            ]
            if missing:
                self._log_step(
                    "mtls_certs_saved",
                    f"Warning: Missing certificates in payload: {', '.join(missing)}",
                )
        except Exception as exc:
            self._log_step("mtls_certs_saved", f"Error writing certificates: {exc}")
            self.update_state(error=str(exc))
            return False

        try:
            self._log_step("capability_token_copy", "Copying capability tokens to DMS user")
            if not self.copy_capability_tokens_to_dms_user():
                self._log_step("capability_token_copy", "Capability token copy failed; aborting")
                self.update_state(error="Capability token copy failed")
                return False
        except Exception as exc:
            self._log_step("capability_token_copy", f"Exception copying capability tokens: {exc}")
            self.update_state(error=str(exc))
            return False

        try:
            self._log_step("capabilities_onboarded", "Running onboard-max.sh to apply compute capabilities")
            result = self.dms_manager.onboard_compute()
            if not result or result.get("status") != "success":
                message = (result or {}).get("message") or "Unknown error"
                self._log_step("capabilities_onboarded", f"Compute onboarding failed: {message}")
                self.update_state(error=f"Compute onboarding failed: {message}")
                return False
            self._log_step(
                "capabilities_onboarded",
                f"Compute onboarding completed: {result.get('message', 'success')}",
            )
            self.update_state(step="capabilities_onboarded", progress=83, last_step="capabilities_applied")
        except Exception as exc:
            self._log_step("capabilities_onboarded", f"Exception during compute onboarding: {exc}")
            self.update_state(error=str(exc))
            return False

        return True
    def copy_capability_tokens_to_dms_user(self) -> bool:
        source_path = Path("/home/ubuntu/.nunet/cap/dms.cap")
        dest_path = Path("/home/nunet/.nunet/cap/dms.cap")
        if not source_path.exists():
            self._log_step("capability_token_copy", f"Source capability file not found: {source_path}")
            return False
        try:
            source_hash = hashlib.sha256(source_path.read_bytes()).hexdigest()
            self._log_step("capability_token_copy", f"Source file SHA256: {source_hash}")
        except Exception as exc:
            self._log_step("capability_token_copy", f"Error calculating source checksum: {exc}")
            return False

        dest_dir = dest_path.parent
        try:
            subprocess.run(["sudo", "mkdir", "-p", str(dest_dir)], check=True, capture_output=True, text=True)
            self._log_step("capability_token_copy", f"Ensured destination directory exists: {dest_dir}")
        except subprocess.CalledProcessError as exc:
            self._log_step("capability_token_copy", "Error creating destination directory", error=exc.stderr)
            return False

        try:
            result = subprocess.run(
                ["sudo", "cp", str(source_path), str(dest_path)],
                check=True,
                capture_output=True,
                text=True,
            )
            self._log_step("capability_token_copy", "Copied capability file", output=result.stdout)
        except subprocess.CalledProcessError as exc:
            self._log_step(
                "capability_token_copy",
                "Error copying capability tokens",
                output=exc.stdout,
                error=exc.stderr,
            )
            return False

        for command in (
            ["sudo", "chown", "nunet:nunet", str(dest_path)],
            ["sudo", "chmod", "644", str(dest_path)],
        ):
            try:
                subprocess.run(command, check=True, capture_output=True, text=True)
                self._log_step("capability_token_copy", f"Executed {' '.join(command)}")
            except subprocess.CalledProcessError as exc:
                self._log_step(
                    "capability_token_copy",
                    f"Error running {' '.join(command)}",
                    output=exc.stdout,
                    error=exc.stderr,
                )
                return False

        try:
            result = subprocess.run(["sudo", "sha256sum", str(dest_path)], check=True, capture_output=True, text=True)
            dest_hash = result.stdout.strip().split()[0]
            self._log_step("capability_token_copy", f"Destination file SHA256: {dest_hash}")
            if dest_hash != source_hash:
                self._log_step(
                    "capability_token_copy",
                    "Checksum mismatch between source and destination capability files",
                )
                return False
        except subprocess.CalledProcessError as exc:
            self._log_step(
                "capability_token_copy",
                "Error verifying destination checksum",
                output=exc.stdout,
                error=exc.stderr,
            )
            return False

        try:
            result = subprocess.run(
                ["sudo", "ls", "-la", str(dest_dir)],
                check=True,
                capture_output=True,
                text=True,
            )
            self._log_step("capability_token_copy", "Capability directory listing", output=result.stdout)
        except subprocess.CalledProcessError as exc:
            self._log_step(
                "capability_token_copy",
                "Error listing capability directory",
                output=exc.stdout,
                error=exc.stderr,
            )
        self._log_step("capability_token_copy", "Capability tokens copied successfully")
        return True

    def restart_dms_service(self) -> bool:
        try:
            self._log_step("dms_restart", "Restarting nunetdms service")
            result = subprocess.run(
                ["sudo", "systemctl", "restart", "nunetdms"],
                check=True,
                capture_output=True,
                text=True,
            )
            self._log_step("dms_restart", "DMS service restarted", output=result.stdout)
            time.sleep(3)
            result = subprocess.run(
                ["sudo", "systemctl", "is-active", "nunetdms"],
                check=True,
                capture_output=True,
                text=True,
            )
            if result.stdout.strip() == "active":
                self._log_step("dms_restart", "DMS service is active")
                return True
            self._log_step("dms_restart", f"Unexpected DMS status: {result.stdout.strip()}")
        except subprocess.CalledProcessError as exc:
            self._log_step(
                "dms_restart",
                "Error managing DMS service",
                output=exc.stdout,
                error=exc.stderr,
            )
        except Exception as exc:
            self._log_step("dms_restart", f"Unexpected error restarting DMS: {exc}")
        return False
    def run_onboarding_steps(self) -> None:
        self.state = self.load_state()
        if self.state is None:
            logger.info("No onboarding state present; nothing to do")
            return
        try:
            step = self.state.get("step", "init")
            if step == "init":
                self.append_log("init", "Transition: init -> select_org", only_on_step_change=True)
                self.update_state(step="select_org")
                return
            if step == "select_org":
                if not self.state.get("org_data"):
                    logger.info("Waiting for organization selection")
                    return
                self.append_log("select_org", "Transition: select_org -> collect_join_data", only_on_step_change=True)
                self.update_state(step="collect_join_data")
                return
            if step == "collect_join_data":
                if not self.state.get("form_data"):
                    logger.info("Waiting for join form data")
                    return
                self.append_log("collect_join_data", "Transition: collect_join_data -> submit_data", only_on_step_change=True)
                self.update_state(step="submit_data")
                return
            if step == "submit_data":
                org_data = self.state.get("org_data") or {}
                form_data = self.state.get("form_data", {})
                dms_did = form_data.get("dms_did")
                peer_id = form_data.get("dms_peer_id")
                if not dms_did or not peer_id:
                    dms_status = get_dms_status_info() or {}
                    dms_did = dms_status.get("dms_did")
                    peer_id = dms_status.get("dms_peer_id")
                if not dms_did or not peer_id:
                    message = "Missing DMS DID or Peer ID. Cannot continue onboarding."
                    logger.error(message)
                    self.append_log("submit_data", message, only_on_step_change=True)
                    self.update_state(error=message)
                    return
                payload = dict(form_data)
                payload.update(
                    {
                        "organization_name": org_data.get("name"),
                        "organization_did": org_data.get("did"),
                        "dms_did": dms_did,
                        "dms_peer_id": peer_id,
                    }
                )
                self.update_state(processing=True)
                try:
                    response = self.api_submit_join(payload)
                    self.update_state(
                        step="join_data_sent",
                        api_status=response.get("status"),
                        api_message=response.get("message"),
                        api_request_id=response.get("request_id"),
                        api_status_token=response.get("status_token"),
                        processing=False,
                    )
                    self.append_log("join_data_sent", "Join data submitted")
                except Exception as exc:
                    self.update_state(
                        step="rejected",
                        rejection_reason=str(exc),
                        last_step="submit_data",
                        processing=False,
                    )
                return
            if step == "join_data_sent":
                request_id = self.state.get("api_request_id")
                status_token = self.state.get("api_status_token")
                if not request_id or not status_token:
                    logger.info("Waiting for API request tracking details")
                    return
                try:
                    status = self.api_check_status(request_id, status_token)
                except Exception as exc:
                    logger.warning("Status poll failed", extra={"error": str(exc)})
                    return
                api_status = status.get("status")
                self.update_state(api_status=api_status)
                if api_status in {"approved", "ready"}:
                    payload = status.get("payload")
                    if payload:
                        self.update_state(step="join_data_received", api_payload=payload, last_step="join_data_sent")
                    else:
                        self.update_state(
                            step="rejected",
                            rejection_reason="No onboarding payload received from API",
                            last_step="join_data_sent",
                        )
                    return
                if api_status in {"pending", "processing", "email_verified"}:
                    logger.info("Onboarding pending approval", extra={"api_status": api_status})
                    return
                self.update_state(
                    step="rejected",
                    rejection_reason=status.get("rejection_reason", status.get("reason", "Unknown")),
                    last_step="join_data_sent",
                )
                return
            if step == "join_data_received":
                payload = self.state.get("api_payload")
                if not payload:
                    self.append_log("join_data_received", "Waiting for API payload", only_on_step_change=True)
                    return
                self.append_log("join_data_received", "Processing post-approval onboarding actions", only_on_step_change=True)
                if self.process_post_approval_payload(payload):
                    self.update_state(step="telemetry_configured", last_step="join_data_received")
                return
            if step == "telemetry_configured":
                self.update_state(step="mtls_certs_saved", last_step="telemetry_configured")
                return
            if step == "mtls_certs_saved":
                self.update_state(step="complete", status="complete", completed=True, last_step="mtls_certs_saved")
                try:
                    org_data = (self.state or {}).get("org_data", {})
                    self.mark_onboarding_complete(org_data.get("name"))
                except Exception as exc:
                    logger.error("Failed to mark onboarding complete", extra={"error": str(exc)})
                return
            if step == "rejected":
                self.append_log("rejected", f"Onboarding rejected: {self.state.get('rejection_reason')}", only_on_step_change=True)
                return
            if step == "complete":
                self.append_log("complete", "Onboarding already complete", only_on_step_change=True)
                return
        except Exception as exc:
            logger.exception("Exception in onboarding state machine", extra={"error": str(exc)})
            self.append_log("error", f"Exception in onboarding: {exc}", only_on_step_change=True)
            self.update_state(error=str(exc))
    def get_onboarding_status(self) -> Dict[str, Any]:
        self.state = self.load_state()
        status = dict(self.state) if self.state is not None else {
            "step": "not_started",
            "progress": 0,
            "status": "not_started",
        }
        status["organization_status"] = {
            "joined": get_joined_organizations_with_names(),
            "joined_details": get_joined_organizations_with_details(),
            "known": load_known_organizations(),
        }
        return status

    def select_organization(self) -> Optional[str]:
        known_orgs = load_known_organizations()
        if not known_orgs:
            print("No known organizations available.")
            return None
        org_list = list(known_orgs.items())
        for idx, (did, name) in enumerate(org_list, start=1):
            print(f"  {idx}. {name} ({did})")
        while True:
            try:
                choice = int(input("Select organization to join [number]: "))
                if 1 <= choice <= len(org_list):
                    return org_list[choice - 1][0]
            except Exception:
                pass
            print("Invalid selection. Please try again.")

    def run_full_onboarding(self) -> Dict[str, Any]:
        results = {
            "status": "success",
            "steps": [],
            "wormhole_code": None,
            "message": "Onboarding completed successfully",
        }
        try:
            self.append_log("update_dms", "Updating DMS to latest version")
            update_result = self.dms_manager.update_dms()
            results["steps"].append(
                {"step": "Update DMS", "status": update_result.get("status"), "message": update_result.get("message")}
            )
            if update_result.get("status") != "success":
                raise RuntimeError(update_result.get("message"))
            self.append_log("restart_dms", "Restarting DMS")
            restart_result = self.dms_manager.restart_dms()
            results["steps"].append(
                {
                    "step": "Restart DMS",
                    "status": restart_result.get("status"),
                    "message": restart_result.get("message"),
                }
            )
            if restart_result.get("status") != "success":
                raise RuntimeError(restart_result.get("message"))
            self.append_log("install_proxy", "Installing proxy and DDNS support")
            self.caddy_proxy_manager.install_systemd_service()
            results["steps"].append(
                {
                    "step": "Install Proxy",
                    "status": "success",
                    "message": "Caddy Proxy Manager installed",
                }
            )
            self.update_state(step="complete", progress=100)
            org_data = self.state.get("org_data", {}) if self.state else {}
            self._archive_onboarding_state(org_data.get("name", "Unknown"))
            self.uninstall_systemd_service()
            return results
        except Exception as exc:
            logger.error("Full onboarding failed", extra={"error": str(exc)})
            results["status"] = "error"
            results["message"] = f"Onboarding failed: {exc}"
            return results

    def _archive_onboarding_state(self, org_name: str) -> None:
        if not self.STATE_PATH.exists():
            return
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_org = "".join(c for c in org_name if c.isalnum() or c in {" ", "-", "_"}).rstrip().replace(" ", "_")
            archive_path = self.STATE_PATH.parent / f"onboarding_state_{safe_org}_{timestamp}.json"
            shutil.move(self.STATE_PATH, archive_path)
            logger.info("Archived onboarding state", extra={"path": str(archive_path)})
        except Exception as exc:
            logger.error("Failed to archive onboarding state", extra={"error": str(exc)})
    def check_dms_ready(self) -> bool:
        try:
            from modules.systemd_helper import systemd_helper

            if not systemd_helper.is_active("nunetdms.service"):
                logger.info("DMS service is not running")
                return False
            dms_status = get_dms_status_info() or {}
            if not dms_status.get("dms_peer_id") or not dms_status.get("dms_did"):
                logger.info("DMS peer ID or DID not available")
                return False
            logger.info("DMS is ready for onboarding")
            return True
        except Exception as exc:
            logger.error("Error checking DMS readiness", extra={"error": str(exc)})
            return False

    def _check_archived_completion(self) -> bool:
        pattern = str(self.STATE_PATH.parent / "onboarding_state_*_*.json")
        try:
            archived_files = glob.glob(pattern)
            if archived_files:
                logger.info(
                    "Archived onboarding files found",
                    extra={"count": len(archived_files), "pattern": pattern},
                )
                return True
            return False
        except Exception as exc:
            logger.error("Error checking archived completion", extra={"error": str(exc)})
            return False

    def is_onboarding_complete(self) -> bool:
        try:
            if self.STATE_PATH.exists():
                state = self.load_state()
                if not state:
                    return False
                if state.get("step") == "complete" or state.get("status") == "complete" or state.get("completed"):
                    return True
            return self._check_archived_completion()
        except Exception as exc:
            logger.error("Error determining onboarding completion", extra={"error": str(exc)})
            return False

    def should_run_onboarding(self) -> bool:
        try:
            if self.is_onboarding_complete():
                logger.info("Onboarding already complete; nothing to run")
                return False
            current_state = self.load_state()
            if current_state is None:
                logger.info("No onboarding state file present; not running service")
                return False
            step = current_state.get("step")
            status = current_state.get("status")
            if step in {"complete", "rejected"} or status in {"complete", "error"}:
                logger.info("Onboarding in terminal state", extra={"step": step, "status": status})
                return False
            if not self.check_dms_ready():
                logger.info("DMS not ready; onboarding should not run")
                return False
            return True
        except Exception as exc:
            logger.error("Error evaluating onboarding run state", extra={"error": str(exc)})
            return False

    def mark_onboarding_complete(self, org_name: Optional[str] = None) -> bool:
        try:
            self.update_state(step="complete", progress=100, completed=True, status="complete")
            if not org_name:
                org_name = ((self.state or {}).get("org_data") or {}).get("name", "Unknown")
            self._archive_onboarding_state(org_name)
            try:
                self.disable_systemd_service()
                self.stop_systemd_service()
                self.append_log("complete", "Onboarding service disabled and stopped")
            except Exception as exc:
                self.append_log("complete", f"Warning: Could not disable onboarding service: {exc}")
            self.append_log("complete", "Onboarding marked as complete")
            return True
        except Exception as exc:
            self.append_log("complete", f"Error marking onboarding complete: {exc}")
            return False\r\n\r\n    def mock_api_submit_join(self, data: Dict[str, Any]) -> Dict[str, Any]:
        import random

        if random.random() < 0.8:
            return {"status": "pending", "request_id": "req123"}
        return {"status": "rejected", "reason": "Manual review failed"}

    def mock_api_check_status(self, request_id: str) -> Dict[str, Any]:
        import random

        if random.random() < 0.7:
            return {"status": "approved"}
        return {"status": "pending"}


class OnboardingManager(OnboardingService):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        if args:
            import warnings

            warnings.warn(
                "Positional arguments for OnboardingManager are deprecated; use keyword arguments instead.",
                DeprecationWarning,
                stacklevel=2,
            )
        super().__init__(*args, **kwargs)


__all__ = ["OnboardingService", "OnboardingManager", "ONBOARDING_STATES"]


