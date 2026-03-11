"""
Caddy Proxy Manager module for NuNet Appliance
"""

import subprocess
import json
import os
import time
from typing import Dict, List, Optional, Set
from pathlib import Path
import logging
from .ddns_manager import DDNSManager, make_dns_label

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("CaddyProxyManager")

class CaddyProxyManager:
    def __init__(self):
        home = os.path.expanduser("~")
        self.caddy_base_dir = os.path.join(home, "nunet", "appliance", "plugins", "caddy")
        self.caddy_config_path = os.path.join(self.caddy_base_dir, "Caddyfile")
        self.caddyfile_container_path = "/etc/caddy/Caddyfile"
        self.caddy_data_dir = os.path.join(self.caddy_base_dir, "data")
        self.caddy_container_name = "nunet-caddy-proxy"
        self.caddy_image = "caddy:2"
        self.last_config = None
        self.ddns_manager = DDNSManager()
        # Load ddns-config.json for default domain, wildcard cert path and URL
        self._config_path = Path.home() / "nunet" / "appliance" / "ddns-client" / "ddns-config.json"
        self.default_domain = "ddns.nunet.network"
        self.wildcard_cert_base_path = Path.home() / "nunet" / "appliance" / "ddns-client" / "certs"
        self.wildcard_cert_server = "https://api01.nunet.network:8443/live"
        try:
            if self._config_path.exists():
                with open(self._config_path) as f:
                    cfg = json.load(f)
                self.default_domain = cfg.get("ddns_domain", self.default_domain)
                self.wildcard_cert_server = cfg.get("wildcard_cert_server", self.wildcard_cert_server)
                cert_path = cfg.get("wildcard_cert_path", "~/nunet/appliance/ddns-client/certs")
                self.wildcard_cert_base_path = Path(cert_path).expanduser()
        except Exception:
            pass
        # Optionally, load the current Caddyfile content:
        if os.path.exists(self.caddy_config_path):
            with open(self.caddy_config_path, "r") as f:
                self.last_config = f.read()
        self.setup_caddy_dirs_and_file()

    def setup_caddy_dirs_and_file(self):
        subprocess.run(["sudo", "mkdir", "-p", os.path.dirname(self.caddy_config_path)], check=True)
        subprocess.run(["sudo", "mkdir", "-p", self.caddy_data_dir], check=True)
        subprocess.run(["sudo", "chown", f"{os.getuid()}:{os.getgid()}", os.path.dirname(self.caddy_config_path)], check=True)
        subprocess.run(["sudo", "chown", f"{os.getuid()}:{os.getgid()}", self.caddy_data_dir], check=True)
        if os.path.isdir(self.caddy_config_path):
            subprocess.run(["sudo", "rm", "-rf", self.caddy_config_path], check=True)
        if not os.path.exists(self.caddy_config_path):
            subprocess.run(["sudo", "touch", self.caddy_config_path], check=True)
            subprocess.run(["sudo", "chown", f"{os.getuid()}:{os.getgid()}", self.caddy_config_path], check=True)
        if os.path.getsize(self.caddy_config_path) == 0:
            with open(self.caddy_config_path, "w") as f:
                f.write(":80, :443 {\n    respond \"Caddy proxy is running\"\n}\n")
            subprocess.run(["sudo", "chown", f"{os.getuid()}:{os.getgid()}", self.caddy_config_path], check=True)

    def get_wildcard_cert_paths(self, domain: str) -> Optional[Dict[str, str]]:
        """Get wildcard certificate paths for a domain if they exist."""
        domain_cert_dir = self.wildcard_cert_base_path / domain
        cert_file = domain_cert_dir / "fullchain.pem"
        key_file = domain_cert_dir / "privkey.pem"
        
        if cert_file.exists() and key_file.exists():
            return {
                "cert": str(cert_file),
                "key": str(key_file)
            }
        return None

    def has_wildcard_certs(self, domain: str) -> bool:
        """Check if wildcard certificates exist for a domain."""
        return self.get_wildcard_cert_paths(domain) is not None

    def get_wildcard_cert_server(self) -> str:
        """Get the server URL for retrieving wildcard certificates."""
        return self.wildcard_cert_server

    def get_domain_cert_dir(self, domain: str) -> Path:
        """Get the certificate directory path for a specific domain."""
        return self.wildcard_cert_base_path / domain

    def download_wildcard_certificates(self, domain: str = None) -> bool:
        """Download wildcard certificates from the certificate server"""
        if domain is None:
            domain = self.default_domain
            
        # Certificate server URLs
        base_url = self.wildcard_cert_server
        fullchain_url = f"{base_url}/{domain}/fullchain.pem"
        privkey_url = f"{base_url}/{domain}/privkey.pem"
        
        # Local certificate paths
        cert_dir = self.get_domain_cert_dir(domain)
        fullchain_path = cert_dir / "fullchain.pem"
        privkey_path = cert_dir / "privkey.pem"
        
        # Client certificate paths for authentication
        client_cert_path = self.wildcard_cert_base_path / "certs" / "client.crt"
        client_key_path = self.wildcard_cert_base_path / "certs" / "client.key"
        ca_bundle_path = self.wildcard_cert_base_path / "certs" / "infra-bundle-ca.crt"
        
        # Check if client certificates exist
        if not all(p.exists() for p in [client_cert_path, client_key_path, ca_bundle_path]):
            logger.warning("Client certificates not found - skipping wildcard certificate download")
            return False
        
        try:
            logger.info(f"Downloading wildcard certificates for domain: {domain}")
            
            # Create certificate directory
            cert_dir.mkdir(parents=True, exist_ok=True)
            
            # Download fullchain.pem
            result = subprocess.run([
                "curl", "-s", "--connect-timeout", "10",
                "--cert", str(client_cert_path),
                "--key", str(client_key_path),
                "--cacert", str(ca_bundle_path),
                fullchain_url
            ], capture_output=True, text=True)
            
            if result.returncode != 0:
                logger.error(f"Failed to download fullchain.pem: {result.stderr}")
                return False
            
            if not result.stdout.startswith("-----BEGIN CERTIFICATE-----"):
                logger.error("Invalid fullchain.pem format received")
                return False
            
            # Download privkey.pem
            result = subprocess.run([
                "curl", "-s", "--connect-timeout", "10",
                "--cert", str(client_cert_path),
                "--key", str(client_key_path),
                "--cacert", str(ca_bundle_path),
                privkey_url
            ], capture_output=True, text=True)
            
            if result.returncode != 0:
                logger.error(f"Failed to download privkey.pem: {result.stderr}")
                return False
            
            if not result.stdout.startswith("-----BEGIN PRIVATE KEY-----"):
                logger.error("Invalid privkey.pem format received")
                return False
            
            # Backup existing certificates if they exist
            if fullchain_path.exists():
                backup_path = fullchain_path.with_suffix(f'.pem.backup.{int(time.time())}')
                fullchain_path.rename(backup_path)
                logger.info(f"Backed up existing fullchain.pem to {backup_path}")
            
            if privkey_path.exists():
                backup_path = privkey_path.with_suffix(f'.pem.backup.{int(time.time())}')
                privkey_path.rename(backup_path)
                logger.info(f"Backed up existing privkey.pem to {backup_path}")
            
            # Save the privkey content before we overwrite result
            privkey_content = result.stdout
            
            # Get the fullchain content again 
            result = subprocess.run([
                "curl", "-s", "--connect-timeout", "10",
                "--cert", str(client_cert_path),
                "--key", str(client_key_path),
                "--cacert", str(ca_bundle_path),
                fullchain_url
            ], capture_output=True, text=True)
            
            fullchain_content = result.stdout
            
            # Write new certificates
            fullchain_path.write_text(fullchain_content)
            privkey_path.write_text(privkey_content)
            
            # Set proper permissions
            fullchain_path.chmod(0o644)
            privkey_path.chmod(0o600)
            
            logger.info(f"Successfully downloaded and installed wildcard certificates for {domain}")
            return True
            
        except Exception as e:
            logger.error(f"Error downloading wildcard certificates: {e}")
            return False

    def ensure_caddy_container(self):
        """Ensure the Caddy container is running with correct config and ports."""
        # Check if running
        result = subprocess.run([
            "docker", "ps", "-q", "-f", f"name={self.caddy_container_name}"
        ], capture_output=True, text=True)
        if not result.stdout.strip():
            # Remove any stopped container with the same name
            subprocess.run(["docker", "rm", self.caddy_container_name], capture_output=True)
            
            # Build docker run command
            docker_cmd = [
                "docker", "run", "-d",
                "--name", self.caddy_container_name,
                "-p", "80:80",
                "-p", "443:443",
                "-v", f"{self.caddy_config_path}:{self.caddyfile_container_path}",
                "-v", f"{self.caddy_data_dir}:/data"
            ]
            
            # Add certificate volume mounts if the cert path exists
            if self.wildcard_cert_base_path.exists():
                docker_cmd.extend([
                    "-v", f"{self.wildcard_cert_base_path}:/certs:ro"
                ])
            
            docker_cmd.append(self.caddy_image)
            
            # Start Caddy container
            subprocess.run(docker_cmd, check=True)

    def get_docker_containers(self) -> List[Dict[str, str]]:
        """Return a list of running Docker containers with their environment variables and network info."""
        try:
            result = subprocess.run([
                "docker", "ps", "-q"
            ], capture_output=True, text=True, check=True)
            container_ids = result.stdout.strip().splitlines()
            containers = []
            for cid in container_ids:
                inspect = subprocess.run([
                    "docker", "inspect", cid
                ], capture_output=True, text=True, check=True)
                info = json.loads(inspect.stdout)[0]
                env = info["Config"].get("Env", [])
                env_dict = dict(e.split("=", 1) for e in env if "=" in e)
                # Get networks and internal IP
                network_settings = info.get("NetworkSettings", {})
                networks = network_settings.get("Networks", {})
                
                # Extract IP address - handle both legacy and modern Docker network formats
                ip_address = None
                # Try legacy format first (for default bridge network) - use .get() to avoid KeyError
                ip_address = network_settings.get("IPAddress")
                if not ip_address:
                    # Try modern format (for custom networks)
                    for network_name, network_info in networks.items():
                        ip_address = network_info.get("IPAddress")
                        if ip_address:
                            break
                ports = info["NetworkSettings"].get("Ports", {})
                containers.append({
                    "id": cid,
                    "name": info["Name"].lstrip("/"),
                    "env": env_dict,
                    "networks": list(networks.keys()),
                    "ports": ports,
                    "ip_address": ip_address
                })
            return containers
        except Exception:
            return []

    def get_proxy_port(self, container: Dict[str, any]) -> int:
        """Determine the port to proxy to for a container."""
        env = container["env"]
        if "DMS_PROXY_PORT" in env:
            try:
                return int(env["DMS_PROXY_PORT"])
            except Exception:
                pass
        # Try to get first exposed port
        ports = container.get("ports", {})
        for port_proto, bindings in ports.items():
            if bindings and isinstance(bindings, list):
                # Use the container port (before /tcp or /udp)
                port = port_proto.split("/")[0]
                try:
                    return int(port)
                except Exception:
                    continue
        return 80  # Default

    def get_proxied_containers(self) -> List[Dict[str, str]]:
        containers = self.get_docker_containers()
        proxied = []
        for c in containers:
            env = c["env"]
            # Check if DDNS is enabled
            if env.get("DMS_DDNS_URL", "false").lower() == "true":
                # Get domain from environment or use configured default
                domain = env.get("DMS_DDNS_DOMAIN", self.default_domain)
                # Construct DDNS URL using container name and domain
                # Replace dots with dashes in container name (same logic as DDNS Manager)
                container_name = c["name"]
                allocation_id = container_name.replace('.', '-')
                if '_' in allocation_id:
                    base, suffix = allocation_id.rsplit('_', 1)
                elif '-' in allocation_id:
                    base, suffix = allocation_id.rsplit('-', 1)
                else:
                    base, suffix = allocation_id, "alloc"
                dns_label = make_dns_label(base, suffix)
                proxy_url = f"{dns_label}.{domain}"
                # Add proxy URL to container info
                c["proxy_url"] = proxy_url
                proxied.append(c)
                # Process DDNS registration
                result = self.ddns_manager.process_container(c["name"])
                if result["status"] == "success":
                    logger.info(f"DDNS configured for {c['name']}: {result['message']}")
                else:
                    logger.error(f"DDNS configuration failed for {c['name']}: {result['message']}")
            # If DDNS is not enabled, check for manual proxy configuration
            elif env.get("DMS_REQUIRE_PROXY", "false").lower() == "true" and "DMS_PROXY_URL" in env:
                c["proxy_url"] = env["DMS_PROXY_URL"]
                proxied.append(c)
        return proxied

    def get_required_networks(self, proxied_containers: List[Dict[str, str]]) -> Set[str]:
        required_networks = set()
        for c in proxied_containers:
            required_networks.update(c["networks"])
        return required_networks

    def get_caddy_networks(self) -> Set[str]:
        result = subprocess.run(
            ["docker", "inspect", self.caddy_container_name],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            return set()
        info = json.loads(result.stdout)[0]
        return set(info["NetworkSettings"]["Networks"].keys())

    def attach_caddy_to_networks(self, required_networks: Set[str]):
        caddy_networks = self.get_caddy_networks()
        for net in required_networks:
            if net not in caddy_networks:
                subprocess.run(["docker", "network", "connect", net, self.caddy_container_name], capture_output=True)

    def detach_caddy_from_unused_networks(self, required_networks: Set[str]):
        caddy_networks = self.get_caddy_networks()
        for net in caddy_networks:
            if net not in required_networks and net != "bridge":
                subprocess.run(["docker", "network", "disconnect", net, self.caddy_container_name], capture_output=True)

    def update_caddy_networks(self, required_networks: Set[str]):
        """Attach/detach Caddy to/from networks as needed. Restart if changed."""
        before = self.get_caddy_networks()
        self.attach_caddy_to_networks(required_networks)
        self.detach_caddy_from_unused_networks(required_networks)
        after = self.get_caddy_networks()
        if before != after:
            # Optionally restart Caddy to ensure DNS is refreshed
            subprocess.run(["docker", "restart", self.caddy_container_name], check=True)

    def update_caddy_config(self):
        """Update the Caddyfile, manage Caddy container, and networks. Rate-limited reloads."""
        containers = self.get_docker_containers()
        proxied = self.get_proxied_containers()
        # Track previous set of proxied container names
        current_names = set(c['name'] for c in proxied)
        if not hasattr(self, '_last_proxied_names'):
            self._last_proxied_names = set()
        added = current_names - self._last_proxied_names
        removed = self._last_proxied_names - current_names
        for name in added:
            logger.info(f"Detected new container to proxy: {name}")
        for name in removed:
            logger.info(f"Container removed from proxying: {name}")
        self._last_proxied_names = current_names

        required_networks = self.get_required_networks(proxied)
        
        # Download wildcard certificates on startup if needed
        if not hasattr(self, '_certs_checked'):
            self.download_wildcard_certificates()
            self._certs_checked = True
        
        self.ensure_caddy_container()
        self.update_caddy_networks(required_networks)
        # Generate and write Caddyfile
        new_config = self.generate_caddyfile(proxied)
        if new_config != self.last_config:
            try:
                with open(self.caddy_config_path, "w") as f:
                    f.write(new_config)
                logger.info("Caddyfile updated to:\n" + new_config)
                subprocess.run(["docker", "restart", self.caddy_container_name], check=True)
                self.last_config = new_config
                return {"status": "success", "message": "Caddy config updated and container restarted."}
            except Exception as e:
                logger.error(f"Failed to update/restart Caddy: {e}")
                return {"status": "error", "message": f"Failed to update/restart Caddy: {e}"}
        else:
            return {"status": "no_change", "message": "No changes to Caddy config."}

    def run_monitor_loop(self, interval: int = 30):
        logger.info("Starting Caddy Proxy Manager monitor loop...")
        try:
            while True:
                logger.info("Checking for containers to proxy...")
                result = self.update_caddy_config()
                logger.info(result["message"])
                time.sleep(interval)
        except KeyboardInterrupt:
            logger.info("Caddy Proxy Manager monitor stopped.")

    @staticmethod
    def systemd_monitor_entry(interval: int = 30):
        """Entry point for systemd service to run the monitor loop."""
        mgr = CaddyProxyManager()
        mgr.setup_caddy_dirs_and_file()
        mgr.run_monitor_loop(interval=interval)

    def get_caddy_proxy_status(self):
        """Return Caddy proxy systemd service status (running/stopped)."""
        try:
            result = subprocess.run(
                ["systemctl", "is-active", "nunet-caddy-proxy-monitor.service"],
                capture_output=True, text=True
            )
            status = result.stdout.strip()
            if status == "active":
                return "Running (systemd)"
            elif status == "inactive":
                return "Stopped (systemd)"
            else:
                return f"{status.capitalize()} (systemd)"
        except Exception:
            return "Unknown"

    def show_proxy_log(self):
        print("\n=== Caddy Proxy Manager Log ===\n")
        try:
            os.system("sudo journalctl -u nunet-caddy-proxy-monitor.service -n 40 --no-pager")
        except Exception as e:
            print(f"Failed to show log: {e}")
        input("\nPress Enter to continue...")

    def show_manager_menu(self):
        """Show menu for managing Caddy Proxy Manager (service is now installed via deb package)."""
        menu_options = {
            "1": ("Show Proxy Manager Log", "📄", self.show_proxy_log),
        }
        while True:
            print("\n=== Manage Caddy Proxy Manager ===")
            print(f"Status: {self.get_caddy_proxy_status()}")
            print("Note: Service is managed by nunet-appliance-web package")
            for key, (label, icon, _) in menu_options.items():
                print(f"{key}) {icon} {label}")
            print("0) 🔙 Return to Appliance Menu")
            choice = input("\nSelect an option: ")
            if choice == "0":
                break
            elif choice in menu_options:
                menu_options[choice][2]()
            else:
                print("Invalid option!")
                input("Press Enter to continue...")

    def generate_caddyfile(self, containers: List[Dict[str, any]]) -> str:
        """Generate a Caddyfile based on containers requiring proxy."""
        caddyfile = ""
        
        # Group containers by domain and wildcard usage for efficient certificate handling
        wildcard_domains = {}
        regular_containers = []
        
        for c in containers:
            if "proxy_url" in c:
                env = c.get('env', {})
                use_wildcard = env.get("DDNS_PROXY_WILDCARD", "false").lower() == "true"
                
                if use_wildcard:
                    # Extract domain from proxy URL
                    proxy_url = c['proxy_url']
                    if '.' in proxy_url:
                        domain_parts = proxy_url.split('.')
                        if len(domain_parts) > 1:
                            domain = '.'.join(domain_parts[1:])
                            if self.has_wildcard_certs(domain):
                                if domain not in wildcard_domains:
                                    wildcard_domains[domain] = []
                                wildcard_domains[domain].append(c)
                                continue
                            else:
                                logger.warning(f"Wildcard certificate requested but not found for domain {domain}")
                
                # Container doesn't use wildcard certs or certs not found
                regular_containers.append(c)
        
        # Generate wildcard certificate blocks
        for domain, domain_containers in wildcard_domains.items():
            # Create a single block for all subdomains using the same wildcard certificate
            subdomain_list = []
            container_configs = []
            
            for c in domain_containers:
                subdomain_list.append(c['proxy_url'])
                port = self.get_proxy_port(c)
                # Use IP address if available, fallback to container name
                # Container names with dots (e.g., .alloc1) may not resolve via Docker DNS
                # Reference: https://forums.docker.com/t/embedded-dns-does-not-resolve-hostnames/42352
                ip_address = c.get('ip_address')
                if ip_address:
                    target = f"{ip_address}:{port}"
                else:
                    # Fallback to container name if IP not available
                    # NOTE: Currently commented out due to Docker DNS issues with dotted names
                    # Keep this code for future use if container name format changes or Docker DNS improves
                    # container_name = c['name']
                    # target = f"{container_name}:{port}"
                    # For now, log error if IP is not available
                    logger.error(f"No IP address available for container {c['name']}, cannot create proxy target")
                    continue
                container_configs.append({
                    'proxy_url': c['proxy_url'],
                    'target': target
                })
            
            # Generate a block that handles all subdomains with the wildcard certificate
            subdomains_str = ", ".join(subdomain_list)
            caddyfile += f"{subdomains_str} {{\n"
            caddyfile += f"  tls /certs/{domain}/fullchain.pem /certs/{domain}/privkey.pem\n"
            
            # Add reverse proxy configuration for each subdomain
            for config in container_configs:
                caddyfile += f"  @{config['proxy_url'].replace('.', '_').replace('-', '_')} host {config['proxy_url']}\n"
                caddyfile += f"  reverse_proxy @{config['proxy_url'].replace('.', '_').replace('-', '_')} {config['target']}\n"
            
            caddyfile += "}\n\n"
            
            logger.info(f"Using wildcard certificate for domain {domain} with subdomains: {subdomain_list}")
        
        # Generate individual blocks for containers not using wildcard certificates
        for c in regular_containers:
            port = self.get_proxy_port(c)
            proxy_url = c['proxy_url']
            # Use IP address if available, fallback to container name
            # Container names with dots (e.g., .alloc1) may not resolve via Docker DNS
            # Reference: https://forums.docker.com/t/embedded-dns-does-not-resolve-hostnames/42352
            ip_address = c.get('ip_address')
            if ip_address:
                target = f"{ip_address}:{port}"
            else:
                # Fallback to container name if IP not available
                # NOTE: Currently commented out due to Docker DNS issues with dotted names
                # Keep this code for future use if container name format changes or Docker DNS improves
                # container_name = c['name']
                # target = f"{container_name}:{port}"
                # For now, skip this container if IP is not available
                logger.error(f"No IP address available for container {c['name']}, skipping proxy configuration")
                continue
            
            caddyfile += f"{proxy_url} {{\n"
            caddyfile += f"  reverse_proxy {target}\n"
            caddyfile += "}\n\n"
        
        return caddyfile

if __name__ == "__main__":
    import sys
    if "--systemd-monitor" in sys.argv:
        # Parse interval if provided
        interval = 30
        if "--interval" in sys.argv:
            try:
                idx = sys.argv.index("--interval")
                interval = int(sys.argv[idx + 1])
            except Exception:
                pass
        CaddyProxyManager.systemd_monitor_entry(interval=interval) 