"""
Onboarding Manager module for NuNet Appliance
Handles the streamlined onboarding process for new users
"""

import subprocess
import os
import time
from typing import Dict, Any
import logging
from .dms_manager import DMSManager
from .organization_manager import OrganizationManager
from .caddy_proxy_manager import CaddyProxyManager
from .ddns_manager import DDNSManager
from .org_utils import load_known_organizations, get_joined_organizations_with_names
from modules.dms_utils import get_dms_status_info, run_dms_command_with_passphrase, get_dms_resource_info
import json
from pathlib import Path
import requests
from datetime import datetime, timedelta
import glob


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("/home/ubuntu/nunet/appliance/onboarding.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("OnboardingManager")


ONBOARDING_STATES = [
    "init", "select_org", "collect_join_data", "submit_data", "join_data_sent",
    "pending_authorization", "join_data_received", "capabilities_applied",
    "telemetry_configured", "mtls_certs_saved", "complete", "rejected"
]

class OnboardingManager:
    STATE_PATH = Path.home() / "nunet" / "appliance" / "onboarding_state.json"
    LOG_PATH = Path.home() / "nunet" / "appliance" / "onboarding.log"
    SERVICE_NAME = "nunet-onboarding.service"

    def __init__(self, use_mock_api=False):
        """Initialize the Onboarding Manager"""
        self.dms_manager = DMSManager()
        self.org_manager = OrganizationManager()
        self.caddy_proxy_manager = CaddyProxyManager()
        self.ddns_manager = DDNSManager()
        self.state = self.load_state()
        self.use_mock_api = use_mock_api
        logger.debug("OnboardingManager initialized. use_mock_api=%s", use_mock_api)

    def log(self, message):
        logger.info(message)

    def load_state(self):
        if self.STATE_PATH.exists():
            try:
                with open(self.STATE_PATH, "r") as f:
                    return json.load(f)
            except Exception:
                # If file is empty or corrupt, return None to indicate no valid state
                return None
        return None

    def save_state(self):
        # Only save if state file exists (created by service)
        if self.STATE_PATH.exists():
            with open(self.STATE_PATH, "w") as f:
                json.dump(self.state, f, indent=2)

    def append_log(self, step, message, only_on_step_change=False):
        # Ensure state is initialized
        if self.state is None:
            self.state = {
                "step": "init",
                "progress": 0,
                "wormhole_code": None,
                "form_data": {},
                "error": None,
                "logs": []
            }
            
        if only_on_step_change:
            # Only log if the step is different from the last log entry
            logs = self.state.get("logs", [])
            if logs and logs[-1]["step"] == step:
                return
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        log_entry = {"timestamp": timestamp, "step": step, "message": message}
        self.state.setdefault("logs", []).append(log_entry)
        self.save_state()

    def update_state(self, **kwargs):
        # Ensure state is initialized
        if self.state is None:
            self.state = {
                "step": "init",
                "progress": 0,
                "wormhole_code": None,
                "form_data": {},
                "error": None,
                "logs": []
            }
        
        step = kwargs.get("step")
        if step:
            self.append_log(step, f"Step changed to {step}", only_on_step_change=True)
        self.state.update(kwargs)
        self.save_state()

    def clear_state(self):
        if self.STATE_PATH.exists():
            self.STATE_PATH.unlink()
        self.state = self.load_state()

    def install_systemd_service(self):
        import sys, tempfile
        python_exec = sys.executable
        script_path = str(Path(__file__).parent.parent / "scripts" / "onboarding_service.py")
        working_dir = str(Path(__file__).parent.parent / "scripts")
        service_content = f"""
[Unit]
Description=NuNet Onboarding Service
After=network.target loadubuntukeyring.service
Requires=loadubuntukeyring.service
target=multi-user.target

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
        service_path = f"/etc/systemd/system/{self.SERVICE_NAME}"
        try:
            with tempfile.NamedTemporaryFile("w", delete=False) as tf:
                tf.write(service_content)
                temp_path = tf.name
            subprocess.run(["sudo", "mv", temp_path, service_path], check=True)
            subprocess.run(["sudo", "chown", "root:root", service_path], check=True)
            subprocess.run(["sudo", "systemctl", "daemon-reload"], check=True)
            subprocess.run(["sudo", "systemctl", "enable", self.SERVICE_NAME], check=True)
            subprocess.run(["sudo", "systemctl", "restart", self.SERVICE_NAME], check=True)
            self.log(f"Systemd service '{self.SERVICE_NAME}' installed and started.")
        except Exception as e:
            self.log(f"Failed to install systemd service: {e}")

    def enable_systemd_service(self):
        """Enable and start the systemd service."""
        try:
            subprocess.run(["sudo", "systemctl", "enable", self.SERVICE_NAME], check=True)
            subprocess.run(["sudo", "systemctl", "start", self.SERVICE_NAME], check=True)
            self.log(f"Systemd service '{self.SERVICE_NAME}' enabled and started.")
        except Exception as e:
            self.log(f"Failed to enable systemd service: {e}")

    def stop_systemd_service(self):
        """Stop the systemd service."""
        try:
            subprocess.run(["sudo", "systemctl", "stop", self.SERVICE_NAME], check=True)
            self.log(f"Systemd service '{self.SERVICE_NAME}' stopped.")
        except Exception as e:
            self.log(f"Failed to stop systemd service: {e}")

    def disable_systemd_service(self):
        """Stop and disable the systemd service (but keep the file)."""
        try:
            subprocess.run(["sudo", "systemctl", "stop", self.SERVICE_NAME], check=True)
            subprocess.run(["sudo", "systemctl", "disable", self.SERVICE_NAME], check=True)
            self.log(f"Systemd service '{self.SERVICE_NAME}' stopped and disabled.")
        except Exception as e:
            self.log(f"Failed to disable systemd service: {e}")

    def uninstall_systemd_service(self):
        service_path = f"/etc/systemd/system/{self.SERVICE_NAME}"
        try:
            subprocess.run(["sudo", "systemctl", "stop", self.SERVICE_NAME], check=True)
            subprocess.run(["sudo", "systemctl", "disable", self.SERVICE_NAME], check=True)
            if os.path.exists(service_path):
                subprocess.run(["sudo", "rm", service_path], check=True)
            subprocess.run(["sudo", "systemctl", "daemon-reload"], check=True)
            self.log(f"Systemd service '{self.SERVICE_NAME}' stopped and uninstalled.")
        except Exception as e:
            self.log(f"Failed to uninstall systemd service: {e}")

    def get_onboarding_api_url(self):
        org_data = self.state.get("org_data") or {}
        org_did = org_data.get("did")
        logger.info(f"Looking up onboarding_api_url for org_did={org_did}")
        known_orgs = load_known_organizations()
        logger.info(f"Loaded known_orgs: {known_orgs}")
        if org_did and org_did in known_orgs:
            org_entry = known_orgs[org_did]
            if isinstance(org_entry, dict):
                api_url = org_entry.get("onboarding_api_url")
                logger.info(f"Found onboarding_api_url: {api_url}")
                return api_url
            logger.warning(f"Org entry for {org_did} is not a dict: {org_entry}")
            return None
        logger.warning(f"No onboarding_api_url found for org_did={org_did}")
        return None

    def api_submit_join(self, data):
        if self.use_mock_api:
            return self.mock_api_submit_join(data)
        
        # Ensure compute is onboarded BEFORE submitting to the API so the payload
        # reflects the current onboarded resources. If already onboarded, this is a no-op.
        try:
            from .dms_utils import get_dms_resource_info
            resource_info_pre = get_dms_resource_info()
            pre_status = resource_info_pre.get('onboarding_status', 'Unknown')
            already_onboarded = isinstance(pre_status, str) and ('ONBOARDED' in pre_status)
            if not already_onboarded:
                self.append_log("submit_data", "Pre-onboarding compute resources with onboard-max.sh ...")
                result = self.dms_manager.onboard_compute()
                if not result or result.get("status") != "success":
                    message = (result or {}).get("message") or "Unknown error"
                    self.append_log("submit_data", f"Pre-onboarding failed: {message}")
                    # Abort early so the API receives correct resource state only when successful
                    raise Exception(f"Pre-onboarding failed: {message}")
                self.append_log("submit_data", "Pre-onboarding completed successfully.")
        except Exception as e:
            logger.exception(f"Exception during pre-onboarding: {e}")
            # Surface error and stop flow here; caller will set rejected state
            raise

        # Collect onboarded resource information before submitting (after pre-onboarding)
        logger.info("Collecting onboarded resource information...")
        self.append_log("submit_data", "Collecting onboarded resource information...")
        
        try:
            resource_info = get_dms_resource_info()
            onboarding_status = resource_info.get('onboarding_status', 'Unknown')
            onboarded_resources = resource_info.get('onboarded_resources', 'Unknown')
            
            # Extract boolean status and clean resource string
            is_onboarded = 'ONBOARDED' in onboarding_status
            clean_resources = onboarded_resources.replace('\033[92m', '').replace('\033[0m', '').replace('\033[91m', '')

            # add the raw DMS block requested
            data['dms_resources'] = resource_info.get('dms_resources', {})
             
            logger.info(f"Resource data collected - Onboarding Status: {is_onboarded}, "
                         f"Onboarded Resources: {clean_resources}, "
                        f"DMS Resources: {data['dms_resources']}"
                         )

            # Add resources data to the payload
            data['resources'] = {
                'onboarding_status': is_onboarded,
                'onboarded_resources': clean_resources
            }
            
            logger.info(f"Resource data collected - Onboarding Status: {is_onboarded}, Onboarded Resources: {clean_resources}")
            self.append_log("submit_data", f"Resource data collected - Onboarding Status: {is_onboarded}, Onboarded Resources: {clean_resources}")
            
        except Exception as e:
            logger.warning(f"Failed to collect resource information: {e}")
            self.append_log("submit_data", f"Warning: Failed to collect resource information: {e}")
            # Continue with onboarding even if resource collection fails
            data['resources'] = {
                'onboarding_status': False,
                'onboarded_resources': 'Unknown (collection failed)'
            }
        
        api_url = self.get_onboarding_api_url()
        if not api_url:
            logger.error("No onboarding_api_url found for selected organization.")
            raise Exception("No onboarding_api_url found for selected organization.")
        try:
            logger.info(f"Submitting onboarding data to {api_url}/onboarding/submit/: {json.dumps(data)}")
            resp = requests.post(f"{api_url}/onboarding/submit/", json=data, timeout=30)
            logger.info(f"API response: {resp.status_code} {resp.text}")
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.exception(f"API error during submit_join: {e}")
            self.append_log("submit_data", f"API error: {e}", only_on_step_change=True)
            raise

    def api_check_status(self, request_id, status_token):
        if self.use_mock_api:
            return self.mock_api_check_status(request_id)
        api_url = self.get_onboarding_api_url()
        if not api_url:
            logger.error("No onboarding_api_url found for selected organization.")
            raise Exception("No onboarding_api_url found for selected organization.")
        try:
            logger.info(f"Polling onboarding status from {api_url}/onboarding/status/{request_id}/ with token {status_token}")
            resp = requests.get(f"{api_url}/onboarding/status/{request_id}/", params={"status_token": status_token}, timeout=10)
            logger.info(f"Status API response: {resp.status_code} {resp.text}")
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.exception(f"API error during check_status: {e}")
            self.append_log("join_data_sent", f"API status check error: {e}", only_on_step_change=True)
            raise


    def generate_and_apply_require_token(self, org_did: str):
        """
        Generate and apply require token with specific capabilities.
        Converts the bash script to Python equivalent.
        """
        from modules.dms_utils import run_dms_command_with_passphrase
        import subprocess
        
        def log_step(step, message, output=None, error=None):
            log_msg = message
            if output:
                log_msg += f"\nOutput: {output.strip()}"
            if error:
                log_msg += f"\nError: {error.strip()}"
            self.append_log(step, log_msg)
            logger.info(f"[{step}] {log_msg}")
        
        try:
            # Calculate expiry date (30 days from now in UTC)
            expiry_date = datetime.utcnow() + timedelta(days=30)
            grant_expiry_date = expiry_date.strftime('%Y-%m-%dT%H:%M:%SZ')
            
            log_step("capabilities_applied", f"Generating require token with expiry: {grant_expiry_date}")
            
            # Generate the require token with specific capabilities
            result = run_dms_command_with_passphrase([
                "nunet", "cap", "grant", "--context", "dms",
                "--cap", "/dms/deployment",
                "--cap", "/broadcast", 
                "--cap", "/public",
                "--topic", "/nunet",
                "--expiry", grant_expiry_date,
                org_did
            ], capture_output=True, text=True, check=True)
            
            require_token = result.stdout.strip()
            log_step("capabilities_applied", f"Generated require token: {require_token}", output=result.stdout)
            
            # Apply the require token
            log_step("capabilities_applied", "🔄 Applying require token...")
            anchor_result = run_dms_command_with_passphrase([
                "nunet", "cap", "anchor", "-c", "dms", "--require", require_token
            ], capture_output=True, text=True, check=True)
            
            log_step("capabilities_applied", "✅ Require token applied successfully", output=anchor_result.stdout)
            return True
            
        except subprocess.CalledProcessError as e:
            log_step("capabilities_applied", "Error generating/applying require token.", output=e.stdout, error=e.stderr)
            self.update_state(error=f"Error generating/applying require token: {e.stderr}")
            return False
        except Exception as e:
            log_step("capabilities_applied", f"Exception generating/applying require token: {e}")
            self.update_state(error=f"Exception generating/applying require token: {e}")
            return False





    def process_post_approval_payload(self, payload: dict):
        """
        Process the onboarding payload after approval:
        - Apply require/provide tokens
        - Set Elasticsearch API key
        - Write certificates to disk
        Enhanced: Log every step, command, output, and error to both onboarding.log and onboarding_state.json.
        Also: Log keyring access for DMS passphrase at the start for debugging.
        """
        from modules.dms_utils import run_dms_command_with_passphrase
        from pathlib import Path
        import subprocess
        import os

        def log_step(step, message, output=None, error=None):
            log_msg = message
            if output:
                log_msg += f"\nOutput: {output.strip()}"
            if error:
                log_msg += f"\nError: {error.strip()}"
            self.append_log(step, log_msg)
            logger.info(f"[{step}] {log_msg}")



        # 1. Generate and apply require token with specific capabilities
        try:
            # Get organization DID from payload or state
            org_did = payload.get("organization_did")
            if not org_did:
                # Try to get from state if not in payload
                org_data = self.state.get("org_data") or {}
                org_did = org_data.get("did")
            
            if org_did:
                log_step("capabilities_applied", f"Generating and applying require token for organization: {org_did}")
                success = self.generate_and_apply_require_token(org_did)
                if not success:
                    return False
            else:
                log_step("capabilities_applied", "No organization DID found. Skipping require token generation.")
        except Exception as e:
            log_step("capabilities_applied", f"Exception in require token generation: {e}")
            self.update_state(error=f"Exception in require token generation: {e}")
            return False


        # 2. Apply provide token (if present)
        try:
            provide_token = payload.get("capability_token")
            if provide_token:
                log_step("capabilities_applied", "Applying provide token...")
                result = run_dms_command_with_passphrase([
                    "nunet", "cap", "anchor", "-c", "dms", "--provide", provide_token
                ], capture_output=True, text=True, check=True)
                log_step("capabilities_applied", "Provide token applied successfully.", output=result.stdout)
            else:
                log_step("capabilities_applied", "No provide token found in payload.")
        except subprocess.CalledProcessError as e:
            log_step("capabilities_applied", "Error applying provide token.", output=e.stdout, error=e.stderr)
            self.update_state(error=f"Error applying provide token: {e.stderr}")
            return False
        except Exception as e:
            log_step("capabilities_applied", f"Exception applying provide token: {e}")
            self.update_state(error=f"Exception applying provide token: {e}")
            return False

        # 3. Set Elasticsearch API key and config
        try:
            elastic_api_key = payload.get("elasticsearch_api_key") or payload.get("elastic_api_key")
            config_path = "/home/nunet/config/dms_config.json"
            if elastic_api_key:
                log_step("capabilities_applied", "Setting Elasticsearch API key...")
                result1 = subprocess.run([
                    "nunet", "--config", config_path, "config", "set",
                    "observability.elasticsearch_api_key", elastic_api_key
                ], capture_output=True, text=True, check=True)
                log_step("capabilities_applied", "Elasticsearch API key set.", output=result1.stdout)
                result2 = subprocess.run([
                    "nunet", "--config", config_path, "config", "set",
                    "observability.elasticsearch_enabled", "true"
                ], capture_output=True, text=True, check=True)
                log_step("capabilities_applied", "Elasticsearch enabled set.", output=result2.stdout)
                result3 = subprocess.run([
                    "nunet", "--config", config_path, "config", "set",
                    "observability.elasticsearch_url", "https://telemetry.nunet.io"
                ], capture_output=True, text=True, check=True)
                log_step("capabilities_applied", "Elasticsearch URL set.", output=result3.stdout)
            else:
                log_step("capabilities_applied", "No Elasticsearch API key found in payload.")
        except subprocess.CalledProcessError as e:
            log_step("capabilities_applied", "Error setting Elasticsearch config.", output=e.stdout, error=e.stderr)
            self.update_state(error=f"Error setting Elasticsearch config: {e.stderr}")
            return False
        except Exception as e:
            log_step("capabilities_applied", f"Exception setting Elasticsearch config: {e}")
            self.update_state(error=f"Exception setting Elasticsearch config: {e}")
            return False

        # 4. Write certificates and enable Caddy proxy
        try:
            cert_dir = Path.home() / "nunet" / "appliance" / "ddns-client" / "certs" / "certs"
            cert_dir.mkdir(parents=True, exist_ok=True)
            client_crt = payload.get("client_crt")
            client_key = payload.get("client_key")
            ca_bundle = payload.get("infra_bundle_crt")  # Corrected key
            written = []
            if client_crt:
                (cert_dir / "client.crt").write_text(client_crt)
                written.append("client.crt")
            if client_key:
                (cert_dir / "client.key").write_text(client_key)
                os.chmod(cert_dir / "client.key", 0o600)
                written.append("client.key")
            if ca_bundle:
                (cert_dir / "infra-bundle-ca.crt").write_text(ca_bundle)
                written.append("infra-bundle-ca.crt")
            log_step("mtls_certs_saved", f"Certificates written: {', '.join(written) if written else 'none'}.")
            # Check for missing certs
            missing = []
            if not client_crt:
                missing.append("client.crt")
            if not client_key:
                missing.append("client.key")
            if not ca_bundle:
                missing.append("infra-bundle-ca.crt")
            if missing:
                log_step("mtls_certs_saved", f"Warning: Missing certificates in payload: {', '.join(missing)}.")
            
            # Enable Caddy proxy service if certificates are available
            if client_crt and client_key and ca_bundle:
                log_step("mtls_certs_saved", "All required certificates available. Enabling Caddy proxy service...")
                try:
                    # Use the CaddyProxyManager to install and start the systemd service
                    self.caddy_proxy_manager.install_systemd_service(interval=30)
                    log_step("mtls_certs_saved", "Caddy proxy manager systemd service installed and started")
                    
                    # Verify the service is running
                    status = self.caddy_proxy_manager.get_caddy_proxy_status()
                    if "Running" in status:
                        log_step("mtls_certs_saved", f"✅ Caddy proxy service is running: {status}")
                    else:
                        log_step("mtls_certs_saved", f"⚠️ Caddy proxy service status: {status}")
                        
                except Exception as e:
                    log_step("mtls_certs_saved", f"Error enabling Caddy proxy service: {e}")
                    # Don't fail the entire process for Caddy service issues
            else:
                log_step("mtls_certs_saved", "Not all certificates available. Skipping Caddy proxy service enablement.")
                
        except Exception as e:
            log_step("mtls_certs_saved", f"Error writing certificates: {e}")
            self.update_state(error=f"Error writing certificates: {e}")
            return False

        # 5. Copy capability tokens to DMS user
        try:
            log_step("capability_token_copy", "Starting capability token copy to DMS user...")
            success = self.copy_capability_tokens_to_dms_user()
            if not success:
                log_step("capability_token_copy", "Capability token copy failed. Aborting onboarding process.")
                self.update_state(error="Capability token copy failed. DMS service cannot access updated capabilities.")
                return False
            log_step("capability_token_copy", "Capability token copy completed successfully.")
        except Exception as e:
            log_step("capability_token_copy", f"Exception during capability token copy: {e}")
            self.update_state(error=f"Exception during capability token copy: {e}")
            return False

        # 6. Onboard compute resources to finalize capability setup
        try:
            log_step("capabilities_onboarded", "Running onboard-max.sh to apply compute capabilities...")
            result = self.dms_manager.onboard_compute()
            if not result or result.get("status") != "success":
                message = (result or {}).get("message") or "Unknown error"
                log_step("capabilities_onboarded", f"Compute onboarding failed: {message}")
                self.update_state(error=f"Compute onboarding failed: {message}")
                return False
            log_step("capabilities_onboarded", f"Compute onboarding completed: {result.get('message', 'success')}")
            self.update_state(step="capabilities_onboarded", progress=83, last_step="capabilities_applied")
        except Exception as e:
            log_step("capabilities_onboarded", f"Exception during compute onboarding: {e}")
            self.update_state(error=f"Exception during compute onboarding: {e}")
            return False

        return True

    def copy_capability_tokens_to_dms_user(self):
        """
        Copy capability tokens from ubuntu user to nunet user (DMS service user)
        This replicates the file copying mechanism from the old join-org.sh process.
        Ensures the DMS service has access to the updated capability tokens.
        """
        import subprocess
        import hashlib
        from pathlib import Path

        def log_step(step, message, output=None, error=None):
            log_msg = message
            if output:
                log_msg += f"\nOutput: {output.strip()}"
            if error:
                log_msg += f"\nError: {error.strip()}"
            self.append_log(step, log_msg)
            logger.info(f"[{step}] {log_msg}")

        try:
            # Source and destination paths
            source_path = "/home/ubuntu/.nunet/cap/dms.cap"
            dest_path = "/home/nunet/.nunet/cap/dms.cap"
            
            # Check if source file exists
            if not os.path.exists(source_path):
                log_step("capability_token_copy", f"Source capability file not found: {source_path}")
                return False
            
            # Calculate source file checksum
            log_step("capability_token_copy", f"Calculating source file checksum: {source_path}")
            try:
                with open(source_path, 'rb') as f:
                    source_hash = hashlib.sha256(f.read()).hexdigest()
                log_step("capability_token_copy", f"Source file SHA256: {source_hash}")
            except Exception as e:
                log_step("capability_token_copy", f"Error calculating source checksum: {e}")
                return False
            
            # Ensure destination directory exists
            dest_dir = Path(dest_path).parent
            try:
                subprocess.run(["sudo", "mkdir", "-p", str(dest_dir)], check=True, capture_output=True, text=True)
                log_step("capability_token_copy", f"Ensured destination directory exists: {dest_dir}")
            except subprocess.CalledProcessError as e:
                log_step("capability_token_copy", "Error creating destination directory", error=e.stderr)
                return False
            
            # Copy file using sudo cp
            log_step("capability_token_copy", f"Copying capability tokens from {source_path} to {dest_path}")
            try:
                result = subprocess.run(["sudo", "cp", source_path, dest_path], 
                                      check=True, capture_output=True, text=True)
                log_step("capability_token_copy", "File copy completed successfully", output=result.stdout)
            except subprocess.CalledProcessError as e:
                log_step("capability_token_copy", "Error copying capability tokens", output=e.stdout, error=e.stderr)
                return False
            
            # Set ownership to nunet:nunet
            log_step("capability_token_copy", "Setting file ownership to nunet:nunet")
            try:
                result = subprocess.run(["sudo", "chown", "nunet:nunet", dest_path], 
                                      check=True, capture_output=True, text=True)
                log_step("capability_token_copy", "Ownership set successfully", output=result.stdout)
            except subprocess.CalledProcessError as e:
                log_step("capability_token_copy", "Error setting file ownership", output=e.stdout, error=e.stderr)
                return False
            
            # Set file permissions to 644
            log_step("capability_token_copy", "Setting file permissions to 644")
            try:
                result = subprocess.run(["sudo", "chmod", "644", dest_path], 
                                      check=True, capture_output=True, text=True)
                log_step("capability_token_copy", "Permissions set successfully", output=result.stdout)
            except subprocess.CalledProcessError as e:
                log_step("capability_token_copy", "Error setting file permissions", output=e.stdout, error=e.stderr)
                return False
            
            # Verify file integrity using checksums
            log_step("capability_token_copy", "Verifying file integrity with checksums")
            try:
                result = subprocess.run(["sudo", "sha256sum", dest_path], 
                                      check=True, capture_output=True, text=True)
                dest_hash = result.stdout.strip().split()[0]
                log_step("capability_token_copy", f"Destination file SHA256: {dest_hash}")
                
                if source_hash == dest_hash:
                    log_step("capability_token_copy", "✅ Capability token copy verified successfully. Checksums match.")
                else:
                    log_step("capability_token_copy", f"❌ Capability token verification failed! Checksums do not match. Source: {source_hash}, Destination: {dest_hash}")
                    return False
            except subprocess.CalledProcessError as e:
                log_step("capability_token_copy", "Error verifying destination checksum", output=e.stdout, error=e.stderr)
                return False
            
            # Log final verification
            try:
                result = subprocess.run(["sudo", "ls", "-la", "/home/nunet/.nunet/cap/"], 
                                      check=True, capture_output=True, text=True)
                log_step("capability_token_copy", "Final capability directory listing:", output=result.stdout)
            except subprocess.CalledProcessError as e:
                log_step("capability_token_copy", "Error listing capability directory", output=e.stdout, error=e.stderr)
                # Don't fail the entire process for this verification step
            
            log_step("capability_token_copy", "✅ Capability tokens successfully copied to DMS user")
            return True          
        except Exception as e:
            log_step("capability_token_copy", f"Unexpected error during capability token copy: {e}")
            return False

    def restart_dms_service(self):
        """Restart DMS service to pick up new capability tokens.
        This is the final step of the onboarding process.
        """
        import subprocess
        import time

        def log_step(step, message, output=None, error=None):
            log_msg = message
            if output:
                log_msg += f"\nOutput: {output.strip()}"
            if error:
                log_msg += f"\nError: {error.strip()}"
            self.append_log(step, log_msg)
            logger.info(f"[{step}] {log_msg}")

        try:
            # Restart DMS service to pick up new capabilities
            log_step("dms_restart", "Starting DMS service to apply all configuration changes...")
            try:
                result = subprocess.run(["sudo", "systemctl", "restart", "nunetdms"], 
                                      check=True, capture_output=True, text=True)
                log_step("dms_restart", "DMS service restarted successfully", output=result.stdout)
            except subprocess.CalledProcessError as e:
                log_step("dms_restart", f"Error restarting DMS service: {e.stderr}", output=e.stdout, error=e.stderr)
                return False
            
            # Wait a moment for DMS to fully start up
            log_step("dms_restart", "Waiting for DMS service to fully start up...")
            time.sleep(3)
            
            # Verify DMS service is running
            try:
                result = subprocess.run(["sudo", "systemctl", "is-active", "nunetdms"], 
                                      check=True, capture_output=True, text=True)
                if result.stdout.strip() == "active":
                    log_step("dms_restart", "✅ DMS service is running and ready")
                else:
                    log_step("dms_restart", f"⚠️ DMS service status: {result.stdout.strip()}")
                    return False
            except subprocess.CalledProcessError as e:
                log_step("dms_restart", f"Error checking DMS service status: {e.stderr}", output=e.stdout, error=e.stderr)
                return False
            
            log_step("dms_restart", "✅ DMS service restart completed successfully - onboarding ready!")
            return True          
        except Exception as e:
            log_step("dms_restart", f"Unexpected error during DMS restart: {e}")
            return False

    def run_onboarding_steps(self):
        self.state = self.load_state()
        
        # If no state file exists, onboarding hasn't started yet
        if self.state is None:
            logger.info("No state file found, onboarding not started")
            return
            
        try:
            step = self.state.get("step", "init")

            if step == "init":
                self.append_log("init", "Transition: init -> select_org", only_on_step_change=True)
                self.update_state(step="select_org")
                return

            if step == "select_org":

                if not self.state.get("org_data"):
                    # Don't log every poll to state file, but log to service log
                    logger.info("Waiting for organization selection...")
                    return
                self.append_log("select_org", "Transition: select_org -> collect_join_data", only_on_step_change=True)
                self.update_state(step="collect_join_data")
                return

            if step == "collect_join_data":
                if not self.state.get("form_data"):
                    logger.info("Waiting for user to fill join form...")
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
                    dms_status = get_dms_status_info()
                    dms_did = dms_status.get("dms_did")
                    peer_id = dms_status.get("dms_peer_id")
                if not dms_did or not peer_id:
                    logger.error(f"Missing DMS DID or Peer ID (dms_did={dms_did}, peer_id={peer_id}). Aborting onboarding.")
                    self.append_log("submit_data", f"ERROR: Missing DMS DID or Peer ID (dms_did={dms_did}, peer_id={peer_id}). Aborting onboarding.", only_on_step_change=True)
                    self.update_state(error="Missing DMS DID or Peer ID. Cannot continue onboarding.")
                    return
                payload = dict(form_data)
                payload.update({
                    "organization_name": org_data.get("name"),
                    "organization_did": org_data.get("did"),
                    "dms_did": dms_did,
                    "peer_id": peer_id
                })
                logger.info(f"Submitting data to API: {json.dumps(payload, indent=2)}")
                self.append_log("submit_data", f"Submitting data to API... Payload: {json.dumps(payload, indent=2)}", only_on_step_change=True)
                try:
                    api_result = self.api_submit_join(payload)
                except Exception as e:
                    logger.exception(f"Exception during API submit_join: {e}")
                    self.update_state(step="rejected", rejection_reason=str(e), last_step="submit_data")
                    return
                request_id = api_result.get("id")
                status_token = api_result.get("status_token")
                status = api_result.get("status")
                logger.info(f"API submit_join result: {api_result}")
                if status in ["pending", "email_sent", "processing", "ready"]:
                    self.append_log("submit_data", f"API returned {status}, moving to join_data_sent", only_on_step_change=True)
                    self.update_state(step="join_data_sent", api_status=status, request_id=request_id, status_token=status_token, last_step="submit_data")
                else:
                    self.append_log("submit_data", f"API rejected: {api_result.get('rejection_reason', api_result.get('reason', 'Unknown'))}", only_on_step_change=True)
                    self.update_state(step="rejected", rejection_reason=api_result.get("rejection_reason", api_result.get("reason", "Unknown")), last_step="submit_data")
                return

            if step == "join_data_sent":
                logger.info("Polling API for approval...")
                request_id = self.state.get("request_id")
                status_token = self.state.get("status_token")
                if not request_id or not status_token:
                    logger.error("Missing request_id or status_token in state.")
                    self.append_log("join_data_sent", "Missing request_id or status_token in state.", only_on_step_change=True)
                    self.update_state(step="rejected", rejection_reason="Missing request_id or status_token", last_step="join_data_sent")
                    return
                try:
                    status = self.api_check_status(request_id, status_token)
                except Exception as e:
                    logger.exception(f"Exception during API check_status: {e}")
                    self.update_state(step="rejected", rejection_reason=str(e), last_step="join_data_sent")
                    return
                api_status = status.get("status")
                logger.info(f"API check_status result: {status}")
                if api_status == "email_verified":
                    self.append_log("join_data_sent", f"Email verified, moving to pending_authorization", only_on_step_change=True)
                    self.update_state(step="pending_authorization", api_status=api_status, last_step="join_data_sent")
                    return
                elif api_status in ["ready", "error", "rejected"]:
                    # Save the payload if present, or use the whole status dict if not
                    api_payload = status.get("payload") or status
                    if api_payload:
                        self.append_log("join_data_sent", f"API status {api_status}, saving onboarding payload and moving to join_data_received", only_on_step_change=True)
                        self.update_state(step="join_data_received", api_status=api_status, api_payload=api_payload, last_step="pending_authorization")
                    else:
                        self.append_log("join_data_sent", f"API status {api_status}, but no payload found!", only_on_step_change=True)
                        self.update_state(step="rejected", rejection_reason="No onboarding payload received from API", last_step="join_data_sent")
                    return
                elif api_status in ["email_sent"]:
                    logs = self.state.get("logs", [])
                    if not logs or not any(l["step"] == "join_data_sent" and "Email verification required" in l["message"] for l in logs):
                        logger.info("Email verification required. Waiting for user to verify email.")
                        self.append_log("join_data_sent", "Email verification required. Waiting for user to verify email.", only_on_step_change=True)
                    # Stay in join_data_sent
                    return
                elif api_status in ["pending", "processing"]:
                    logger.info(f"Still waiting for API approval... (status={api_status})")
                    # Don't log every poll to state file
                    return
                else:
                    logger.error(f"API rejected: {status.get('rejection_reason', status.get('reason', 'Unknown'))}")
                    self.append_log("join_data_sent", f"API rejected: {status.get('rejection_reason', status.get('reason', 'Unknown'))}", only_on_step_change=True)
                    self.update_state(step="rejected", rejection_reason=status.get("rejection_reason", status.get("reason", "Unknown")), last_step="join_data_sent")
                    return

            if step == "pending_authorization":
                logger.info("Polling API for approval in pending_authorization...")
                request_id = self.state.get("request_id")
                status_token = self.state.get("status_token")
                if not request_id or not status_token:
                    logger.error("Missing request_id or status_token in state.")
                    self.append_log("pending_authorization", "Missing request_id or status_token in state.", only_on_step_change=True)
                    self.update_state(step="rejected", rejection_reason="Missing request_id or status_token", last_step="pending_authorization")
                    return
                try:
                    status = self.api_check_status(request_id, status_token)
                except Exception as e:
                    logger.exception(f"Exception during API check_status: {e}")
                    self.update_state(step="rejected", rejection_reason=str(e), last_step="pending_authorization")
                    return
                api_status = status.get("status")
                logger.info(f"API check_status result (pending_authorization): {status}")
                if api_status in ["ready", "error", "rejected"]:
                    # Save the payload if present, or use the whole status dict if not
                    api_payload = status.get("payload") or status
                    if api_payload:
                        self.append_log("pending_authorization", f"API status {api_status}, saving onboarding payload and moving to join_data_received", only_on_step_change=True)
                        self.update_state(step="join_data_received", api_status=api_status, api_payload=api_payload, last_step="pending_authorization")
                    else:
                        self.append_log("pending_authorization", f"API status {api_status}, but no payload found!", only_on_step_change=True)
                        self.update_state(step="rejected", rejection_reason="No onboarding payload received from API", last_step="pending_authorization")
                    return
                elif api_status in ["pending", "processing", "email_verified"]:
                    logger.info(f"Still waiting for API approval in pending_authorization... (status={api_status})")
                    # Stay in pending_authorization
                    return
                else:
                    logger.error(f"API rejected: {status.get('rejection_reason', status.get('reason', 'Unknown'))}")
                    self.append_log("pending_authorization", f"API rejected: {status.get('rejection_reason', status.get('reason', 'Unknown'))}", only_on_step_change=True)
                    self.update_state(step="rejected", rejection_reason=status.get("rejection_reason", status.get("reason", "Unknown")), last_step="pending_authorization")
                    return

            if step == "join_data_received":
                # Expect the API payload to be present in state['api_payload']
                api_payload = self.state.get("api_payload")
                if not api_payload:
                    self.append_log("join_data_received", "No API payload found. Waiting for payload...", only_on_step_change=True)
                    return
                self.append_log("join_data_received", "Processing post-approval onboarding actions...", only_on_step_change=True)
                success = self.process_post_approval_payload(api_payload)
                if success:
                    self.update_state(step="capabilities_onboarded", progress=83, last_step="join_data_received")
                else:
                    # Error already logged and state updated in process_post_approval_payload
                    return
                return

            if step == "capabilities_applied":
                # Legacy behavior: immediately escalate to the new compute onboarding step.
                self.append_log("capabilities_applied", "Advancing to capability onboarding...", only_on_step_change=True)
                self.update_state(step="capabilities_onboarded", progress=83, last_step="capabilities_applied")
                return

            if step == "capabilities_onboarded":
                self.append_log("capabilities_onboarded", "Configuring telemetry...", only_on_step_change=True)
                # If telemetry config is part of the API payload, handle here. For now, just advance.
                self.update_state(step="telemetry_configured", mtls_status="saved", last_step="capabilities_onboarded")
                return

            if step == "telemetry_configured":
                self.append_log("telemetry_configured", "Finishing up, moving to mtls_certs_saved", only_on_step_change=True)
                self.update_state(step="mtls_certs_saved", last_step="telemetry_configured")
                return

            if step == "mtls_certs_saved":
                self.append_log("mtls_certs_saved", "Onboarding complete!", only_on_step_change=True)
                self.update_state(step="complete", status="complete", completed=True, last_step="mtls_certs_saved")
                
                # Mark onboarding as complete for session management
                try:
                    org_data = self.state.get("org_data", {})
                    org_name = org_data.get("name", "Unknown")
                    self.mark_onboarding_complete(org_name)
                    logger.info("Onboarding marked as complete for session management")
                except Exception as e:
                    logger.error(f"Error marking onboarding complete: {e}")
                return

            if step == "rejected":
                self.append_log("rejected", f"Onboarding rejected: {self.state.get('rejection_reason')}", only_on_step_change=True)
                return

            if step == "complete":
                self.append_log("complete", "Onboarding already complete.", only_on_step_change=True)
                return

        except Exception as e:
            logger.exception(f"Exception in onboarding: {e}")
            self.append_log("error", f"Exception in onboarding: {e}", only_on_step_change=True)
            self.update_state(error=str(e))

    def get_onboarding_status(self):
        self.state = self.load_state()  # Always reload from disk!
        if self.state is None:
            status = {
                "step": "not_started",
                "progress": 0,
                "status": "not_started"
            }
        else:
            status = dict(self.state)
        
        # Always include organization status regardless of onboarding state
        from modules.org_utils import get_joined_organizations_with_names, get_joined_organizations_with_details, load_known_organizations
        status['organization_status'] = {
            "joined": get_joined_organizations_with_names(),
            "joined_details": get_joined_organizations_with_details(),
            "known": load_known_organizations()
        }
        return status

    def select_organization(self) -> str:
        """Prompt user to select an organization from known orgs."""
        known_orgs = load_known_organizations()
        if not known_orgs:
            print("No known organizations available.")
            return None
        print("\nAvailable Organizations:")
        org_list = list(known_orgs.items())
        for idx, (did, name) in enumerate(org_list, 1):
            print(f"  {idx}. {name} ({did})")
        while True:
            try:
                choice = int(input("Select organization to join [number]: "))
                if 1 <= choice <= len(org_list):
                    return org_list[choice-1][0]
            except Exception:
                pass
            print("Invalid selection. Please try again.")

    def run_full_onboarding(self) -> Dict[str, Any]:
        """
        Run the complete onboarding process:
        1. Update DMS
        2. Restart DMS
        3. Select and join organization
        4. Install Proxy and DDNS support
        """
        results = {
            "status": "success",
            "steps": [],
            "wormhole_code": None,
            "message": "Onboarding completed successfully"
        }

        try:
            # Pre-flight: Fetch DMS status information
            self.log("Pre-flight: Fetching DMS status information")
            try:
                dms_status_info = get_dms_status_info()
                dms_resource_info = get_dms_resource_info()
                
                if not dms_status_info or not dms_status_info.get('dms_peer_id'):
                    self.log("Warning: DMS status info not available")
                
                if not dms_resource_info:
                    self.log("Warning: DMS resource info not available")
                
                # Store DMS info in state for later use
                self.update_state(
                    dms_status_info=dms_status_info,
                    dms_resource_info=dms_resource_info
                )
                
            except Exception as e:
                self.log(f"Warning: Failed to fetch DMS status info: {e}")
            
            # Step 1: Update DMS
            self.update_state(step="update_dms", progress=25)
            self.log("Updating DMS to latest version...")
            update_result = self.dms_manager.update_dms()
            results["steps"].append({
                "step": "Update DMS",
                "status": update_result["status"],
                "message": update_result["message"]
            })
            if update_result["status"] != "success":
                raise Exception(f"DMS update failed: {update_result['message']}")

            # Step 2: Restart DMS
            self.update_state(step="restart_dms", progress=50)
            self.log("Restarting DMS...")
            restart_result = self.dms_manager.restart_dms()
            results["steps"].append({
                "step": "Restart DMS",
                "status": restart_result["status"],
                "message": restart_result["message"]
            })
            if restart_result["status"] != "success":
                raise Exception(f"DMS restart failed: {restart_result['message']}")

            # Step 3: Select and join organization
            self.update_state(step="join_org", progress=65)
            self.log("Selecting organization to join...")
            org_did = self.select_organization()
            if not org_did:
                raise Exception("No organization selected.")
            join_result = self.org_manager.join_organization(org_did)
            results["steps"].append({
                "step": "Join Organization",
                "status": join_result["status"],
                "message": join_result["message"]
            })
            if join_result["status"] != "success":
                raise Exception(f"Organization join failed: {join_result['message']}")

            # Step 4: Install Proxy and DDNS support
            self.update_state(step="install_proxy", progress=90)
            self.log("Installing Proxy and DDNS support...")
            self.caddy_proxy_manager.install_systemd_service()
            results["steps"].append({
                "step": "Install Proxy",
                "status": "success",
                "message": "Caddy Proxy Manager installed"
            })

            self.update_state(step="complete", progress=100)
            self.log("Onboarding completed successfully!")
            
            # Archive state with organization name and date
            org_data = self.state.get("org_data", {})
            org_name = org_data.get("name", "Unknown")
            self._archive_onboarding_state(org_name)
            
            self.uninstall_systemd_service()
            return results

        except Exception as e:
            logger.error(f"Onboarding failed: {str(e)}")
            results["status"] = "error"
            results["message"] = f"Onboarding failed: {str(e)}"
            return results
    
    def _archive_onboarding_state(self, org_name: str):
        """Archive the onboarding state file with organization name and date."""
        try:
            if not self.STATE_PATH.exists():
                return
            
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            # Create archive filename
            safe_org_name = "".join(c for c in org_name if c.isalnum() or c in (' ', '-', '_')).rstrip()
            safe_org_name = safe_org_name.replace(' ', '_')
            archive_name = f"onboarding_state_{safe_org_name}_{timestamp}.json"
            archive_path = self.STATE_PATH.parent / archive_name
            
            # Rename (move) the current state file so a fresh one will be created next run
            import shutil
            shutil.move(self.STATE_PATH, archive_path)
            
            self.log(f"Onboarding state archived to: {archive_path}")
            
        except Exception as e:
            self.log(f"Error archiving onboarding state: {e}")
    
    def check_dms_ready(self):
        """Check if DMS service is running and has valid peer information.
        This is core onboarding business logic that belongs here.
        """
        try:
            # Check if DMS service is running
            from modules.systemd_helper import systemd_helper
            if not systemd_helper.is_active("nunetdms.service"):
                logger.info("DMS service is not running")
                return False
            
            # Check DMS status and resource info
            dms_status = get_dms_status_info()
            dms_resource = get_dms_resource_info()
            
            if not dms_status:
                logger.info("DMS status info not available")
                return False
                
            if not dms_status.get('dms_peer_id'):
                logger.info("DMS peer ID not available")
                return False
                
            if not dms_status.get('dms_did'):
                logger.info("DMS DID not available")
                return False
            
            logger.info("DMS is ready for onboarding")
            return True          
        except Exception as e:
            logger.error(f"Error checking DMS readiness: {e}")
            return False

    def _check_archived_completion(self):
        """
        Check for archived onboarding files to determine completion status.
        Returns True if archived files exist, indicating previous completion.
        """
        try:
            archive_pattern = str(self.STATE_PATH.parent / "onboarding_state_*_*.json")
            logger.debug(f"OnboardingManager: Looking for archived files with pattern: {archive_pattern}")
            
            archived_files = glob.glob(archive_pattern)
            logger.debug(f"OnboardingManager: Found archived files: {archived_files}")
            
            if archived_files:
                logger.info(f"OnboardingManager: Found {len(archived_files)} archived onboarding files, indicating completion")
                return True
            else:
                logger.debug("OnboardingManager: No archived onboarding files found")
            return False
        except Exception as e:
            logger.error(f"OnboardingManager: Error checking archived completion: {e}", exc_info=True)
            return False

    def is_onboarding_complete(self) -> bool:
        """
        Check if onboarding has been completed.
        Enhanced to check both current state file and archived files.
        """
        try:
            logger.debug("OnboardingManager: Checking if onboarding is complete...")
            
            # Check current state file
            if self.STATE_PATH.exists():
                logger.debug(f"OnboardingManager: Current state file exists at {self.STATE_PATH}")
                state = self.load_state()
                if state is None:
                    logger.debug("OnboardingManager: State file exists but is invalid")
                    return False
                    
                logger.debug(f"OnboardingManager: Current state: {state}")
                
                step = state.get('step')
                status = state.get('status')
                completed = state.get('completed')
                
                logger.debug(f"OnboardingManager: step={step}, status={status}, completed={completed}")
                
                if step == 'complete' or status == 'complete' or completed:
                    logger.info("OnboardingManager: Onboarding complete according to current state file")
                    return True
                else:
                    logger.debug("OnboardingManager: Current state file indicates onboarding not complete")
            else:
                logger.debug(f"OnboardingManager: Current state file does not exist at {self.STATE_PATH}")
            
            # Check archived files
            logger.debug("OnboardingManager: Checking for archived completion...")
            if self._check_archived_completion():
                logger.info("OnboardingManager: Onboarding complete according to archived files")
                return True
            else:
                logger.debug("OnboardingManager: No archived completion found")
                
            logger.debug("OnboardingManager: Onboarding is not complete")
            return False
            
        except Exception as e:
            logger.error(f"OnboardingManager: Error checking onboarding completion: {e}", exc_info=True)
            return False

    def should_run_onboarding(self):
        """
        Determine if onboarding should proceed.
        Returns False if already complete, True if should proceed.
        """
        try:
            # Check if already complete (including archived files)
            if self.is_onboarding_complete():
                logger.info("Onboarding already complete, should not run")
                return False

            # Check current state - if we're in a terminal state, don't restart
            current_state = self.load_state()
            if current_state is None:
                logger.info("No state file found, onboarding should not run")
                return False
                
            current_step = current_state.get("step")
            current_status = current_state.get("status")

            # If we're in a terminal state, don't restart
            if current_step in ["complete", "rejected"] or current_status in ["complete", "error"]:
                logger.info(f"Onboarding in terminal state: step={current_step}, status={current_status}")
                return False

            # Check if DMS is ready
            if not self.check_dms_ready():
                logger.info("DMS not ready, should not run onboarding")
                return False

            logger.info("Onboarding should proceed - not complete and DMS is ready")
            return True
        except Exception as e:
            logger.error(f"Error determining if onboarding should run: {e}")
            return False

    def mark_onboarding_complete(self, org_name: str = None) -> bool:
        """Mark onboarding as complete and archive state."""
        try:
            self.update_state(step="complete", progress=100, completed=True, status="complete")
            
            # Always archive; derive org name from state if not provided
            if not org_name:
                try:
                    org_name = (self.state.get("org_data") or {}).get("name") or "Unknown"
                except Exception:
                    org_name = "Unknown"
            self._archive_onboarding_state(org_name)
            
            # Disable and stop the onboarding service since it's no longer needed
            try:
                self.disable_systemd_service()
                self.stop_systemd_service()
                self.log("Onboarding service disabled and stopped")
            except Exception as e:
                self.log(f"Warning: Could not disable/stop onboarding service: {e}")
            
            self.log("Onboarding marked as complete")
            return True          
        except Exception as e:
            self.log(f"Error marking onboarding complete: {e}")
            return False

    # --- Mock API ---
    def mock_api_submit_join(self, data):
        # Simulate API processing and approval
        import random
        if random.random() < 0.8:
            return {"status": "pending", "request_id": "req123"}
        else:
            return {"status": "rejected", "reason": "Manual review failed"}

    def mock_api_check_status(self, request_id):
        import random
        if random.random() < 0.7:
            return {"status": "approved"}
        else:
            return {"status": "pending"} 
