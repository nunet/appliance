"""
DDNS (Dynamic DNS) management module for NuNet Appliance
"""

import os
import time
import subprocess
import logging
import json
from pathlib import Path
from typing import Dict, Optional, Tuple
from .docker_manager import DockerManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("DDNSManager")

def make_dns_label(allocation_id, suffix, first=15, last=15):
    # Remove any non-alphanumeric characters except dash from allocation_id
    allocation_id = allocation_id.replace('_', '').replace('-', '')
    suffix = suffix.replace('_', '-')
    if len(allocation_id) <= first + last:
        truncated = allocation_id
    else:
        truncated = f"{allocation_id[:first]}-{allocation_id[-last:]}"
    return f"{truncated}-{suffix}"

class DDNSManager:
    def __init__(self):
        self.certs_dir = Path.home() / "nunet" / "appliance" / "ddns-client" / "certs" / "certs"
        self.domain = None
        self.hostname = None
        self.verify_interval = 300  # 5 minutes default
        self.verify_timeout = 3600  # 1 hour default
        self.docker_manager = DockerManager()
        # Read API server from config file
        config_path = Path.home() / "nunet" / "appliance" / "ddns-client" / "ddns-config.json"
        if config_path.exists():
            try:
                with open(config_path) as f:
                    config = json.load(f)
                self.api_server = config.get("ddns_api_server", "https://api.parallelvector.com:8080")
            except Exception:
                self.api_server = "https://api.parallelvector.com:8080"
        else:
            self.api_server = "https://api.parallelvector.com:8080"

    def _get_container_info(self, container_name: str) -> Optional[Dict]:
        """Get container information including environment variables"""
        try:
            result = subprocess.run(
                ["docker", "inspect", container_name],
                capture_output=True,
                text=True,
                check=True
            )
            info = json.loads(result.stdout)[0]
            env = info["Config"].get("Env", [])
            env_dict = dict(e.split("=", 1) for e in env if "=" in e)
            return {
                "name": info["Name"].lstrip("/"),
                "env": env_dict,
                "ip": info["NetworkSettings"]["IPAddress"]
            }
        except Exception as e:
            logger.error(f"Failed to get container info: {e}")
            return None

    def _get_public_ip(self) -> Optional[str]:
        """Get the public IP address"""
        try:
            result = subprocess.run(
                ["curl", "-s", "https://api.ipify.org"],
                capture_output=True,
                text=True,
                check=True
            )
            return result.stdout.strip()
        except Exception as e:
            logger.error(f"Failed to get public IP: {e}")
            return None

    def _verify_dns_record(self, hostname: str, expected_ip: str) -> bool:
        """Verify DNS record using dig"""
        try:
            result = subprocess.run(
                ["dig", "+short", hostname],
                capture_output=True,
                text=True,
                check=True
            )
            resolved_ip = result.stdout.strip()
            return resolved_ip == expected_ip
        except Exception as e:
            logger.error(f"Failed to verify DNS record: {e}")
            return False

    def register_ddns(self, container_name: str) -> Dict[str, str]:
        """Register or update DDNS record for a container"""
        container_info = self._get_container_info(container_name)
        if not container_info:
            return {"status": "error", "message": "Failed to get container info"}

        env = container_info["env"]
        if env.get("DMS_DDNS_URL", "false").lower() != "true":
            return {"status": "skipped", "message": "DDNS not enabled for this container"}

        # Get the domain from environment or use default
        self.domain = env.get("DMS_DDNS_DOMAIN", "ddns.parallelvector.com")
        
        # Use container name as allocation id and get suffix (after last underscore or dash)
        allocation_id = container_name
        # Try to extract suffix after last underscore or dash
        if '_' in allocation_id:
            base, suffix = allocation_id.rsplit('_', 1)
        elif '-' in allocation_id:
            base, suffix = allocation_id.rsplit('-', 1)
        else:
            base, suffix = allocation_id, "alloc"
        dns_label = make_dns_label(base, suffix)
        full_hostname = f"{dns_label}.{self.domain}"

        # Get public IP
        public_ip = self._get_public_ip()
        if not public_ip:
            return {"status": "error", "message": "Failed to get public IP"}

        # Make the API request to update DDNS with full hostname
        try:
            response = subprocess.run(
                [
                    "curl", "-sS", "-X", "POST",
                    f"{self.api_server}/update",
                    "--cacert", str(self.certs_dir / "infra-bundle-ca.crt"),
                    "--cert", str(self.certs_dir / "client.crt"),
                    "--key", str(self.certs_dir / "client.key"),
                    "-H", "Content-Type: application/json",
                    "-d", json.dumps({
                        "hostname": full_hostname,  # Send full hostname (truncated)
                        "ip": public_ip
                    }),
                    "-w", "\n%{http_code}"
                ],
                capture_output=True,
                text=True,
                check=True
            )
            
            # Parse response
            response_body, status_code = response.stdout.rsplit("\n", 1)
            if status_code == "200":
                logger.info(f"Successfully registered DDNS record for {full_hostname}")
                return {"status": "success", "message": f"DDNS record registered for {full_hostname}"}
            else:
                logger.error(f"Failed to register DDNS record: {response_body}")
                return {"status": "error", "message": f"Failed to register DDNS record: {response_body}"}
        except Exception as e:
            logger.error(f"Error registering DDNS record: {e}")
            return {"status": "error", "message": f"Error registering DDNS record: {str(e)}"}

    def verify_and_wait(self, container_name: str, expected_ip: str) -> Tuple[bool, str]:
        """Verify DNS record and wait for propagation"""
        # Use the same DNS label logic as registration
        allocation_id = container_name
        if '_' in allocation_id:
            base, suffix = allocation_id.rsplit('_', 1)
        elif '-' in allocation_id:
            base, suffix = allocation_id.rsplit('-', 1)
        else:
            base, suffix = allocation_id, "alloc"
        dns_label = make_dns_label(base, suffix)
        full_hostname = f"{dns_label}.{self.domain}"
        start_time = time.time()
        while time.time() - start_time < self.verify_timeout:
            if self._verify_dns_record(full_hostname, expected_ip):
                return True, f"DNS record verified for {full_hostname}"
            logger.info(f"Waiting for DNS propagation... ({int(time.time() - start_time)}s elapsed)")
            time.sleep(self.verify_interval)
        return False, f"DNS verification timed out after {self.verify_timeout}s"

    def process_container(self, container_name: str) -> Dict[str, str]:
        """Process a container for DDNS registration"""
        # Register DDNS
        result = self.register_ddns(container_name)
        if result["status"] != "success":
            return result

        # Get public IP for verification
        public_ip = self._get_public_ip()
        if not public_ip:
            return {"status": "error", "message": "Failed to get public IP for verification"}

        # Verify DNS record
        verified, message = self.verify_and_wait(container_name, public_ip)
        if not verified:
            return {"status": "error", "message": message}

        return {
            "status": "success",
            "message": f"Successfully configured DDNS for {container_name}"
        }

    def list_ddns_containers(self) -> Dict[str, str]:
        """List containers with DDNS enabled"""
        result = self.docker_manager.get_running_containers()
        if result["status"] != "success" or not result["containers"]:
            return {
                "status": "info",
                "message": "No containers are currently running."
            }
        
        ddns_containers = []
        for container in result["containers"]:
            # Get container info with environment variables
            container_info = self._get_container_info(container["name"])
            if container_info and container_info["env"].get("DMS_DDNS_URL", "false").lower() == "true":
                ddns_containers.append(container_info)
        
        if not ddns_containers:
            return {
                "status": "info",
                "message": "No DDNS-enabled containers found."
            }
        
        message = "DDNS-enabled containers:\n"
        for container in ddns_containers:
            env = container["env"]
            message += f"\nContainer: {container['name']}\n"
            message += f"DDNS Domain: {env.get('DMS_DDNS_DOMAIN', 'nunet.io')}\n"
            message += f"Proxy URL: {env.get('DMS_PROXY_URL', 'Not configured')}\n"
        
        return {
            "status": "success",
            "message": message
        }

    def force_ddns_update(self, container_name: str = None) -> Dict[str, str]:
        """Force DDNS update for a specific container or show selection menu"""
        result = self.docker_manager.get_running_containers()
        if result["status"] != "success" or not result["containers"]:
            return {
                "status": "error",
                "message": "No containers are currently running."
            }
        
        ddns_containers = []
        for container in result["containers"]:
            # Get container info with environment variables
            container_info = self._get_container_info(container["name"])
            if container_info and container_info["env"].get("DMS_DDNS_URL", "false").lower() == "true":
                ddns_containers.append(container_info)
        
        if not ddns_containers:
            return {
                "status": "error",
                "message": "No DDNS-enabled containers found."
            }
        
        if container_name:
            # If container name is provided, find and process it
            container = next((c for c in ddns_containers if c["name"] == container_name), None)
            if not container:
                return {
                    "status": "error",
                    "message": f"Container {container_name} not found or not DDNS-enabled."
                }
            result = self.process_container(container["name"])
            return {
                "status": result["status"],
                "message": f"Result: {result['message']}"
            }
        else:
            # Return list of containers for menu to display
            return {
                "status": "menu",
                "message": "Select a container to update:",
                "containers": ddns_containers
            } 