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
        # Load ddns-config.json for default domain
        self._config_path = Path.home() / "nunet" / "appliance" / "ddns-client" / "ddns-config.json"
        self.default_domain = "ddns.nunet.network"
        try:
            if self._config_path.exists():
                with open(self._config_path) as f:
                    cfg = json.load(f)
                self.default_domain = cfg.get("ddns_domain", self.default_domain)
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

    def ensure_caddy_container(self):
        """Ensure the Caddy container is running with correct config and ports."""
        # Check if running
        result = subprocess.run([
            "docker", "ps", "-q", "-f", f"name={self.caddy_container_name}"
        ], capture_output=True, text=True)
        if not result.stdout.strip():
            # Remove any stopped container with the same name
            subprocess.run(["docker", "rm", self.caddy_container_name], capture_output=True)
            # Start Caddy container
            subprocess.run([
                "docker", "run", "-d",
                "--name", self.caddy_container_name,
                "-p", "80:80",
                "-p", "443:443",
                "-v", f"{self.caddy_config_path}:{self.caddyfile_container_path}",
                "-v", f"{self.caddy_data_dir}:/data",
                self.caddy_image
            ], check=True)

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
                networks = info["NetworkSettings"]["Networks"]
                ip_address = next((networks[n]["IPAddress"] for n in networks if networks[n]["IPAddress"]), None)
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

    def install_systemd_service(self, interval: int = 30):
        """Install or update a systemd service to run the Caddy Proxy Manager monitor loop in the background."""
        import sys
        import tempfile
        service_name = "nunet-caddy-proxy-monitor.service"
        python_exec = sys.executable
        script_path = os.path.abspath(__file__)
        # Set WorkingDirectory to the parent of modules (i.e., /home/ubuntu/menu)
        working_dir = os.path.dirname(os.path.dirname(script_path))
        service_content = f"""
[Unit]
Description=NuNet Caddy Proxy Manager Monitor
After=docker.service
Requires=docker.service

[Service]
Type=simple
Restart=always
User=ubuntu
WorkingDirectory={working_dir}
ExecStart={python_exec} -m modules.caddy_proxy_manager --systemd-monitor --interval {interval}

[Install]
WantedBy=multi-user.target
"""
        service_path = f"/etc/systemd/system/{service_name}"
        try:
            with tempfile.NamedTemporaryFile("w", delete=False) as tf:
                tf.write(service_content)
                temp_path = tf.name
            subprocess.run(["sudo", "mv", temp_path, service_path], check=True)
            subprocess.run(["sudo", "chown", "root:root", service_path], check=True)
            subprocess.run(["sudo", "systemctl", "daemon-reload"], check=True)
            subprocess.run(["sudo", "systemctl", "enable", service_name], check=True)
            subprocess.run(["sudo", "systemctl", "restart", service_name], check=True)
            print(f"Systemd service '{service_name}' installed and started.")
        except Exception as e:
            print(f"Failed to install systemd service: {e}")

    def uninstall_systemd_service(self):
        """Stop and uninstall the systemd service, but only if no containers require proxy."""
        service_name = "nunet-caddy-proxy-monitor.service"
        service_path = f"/etc/systemd/system/{service_name}"
        # Check for containers requiring proxy
        containers = self.get_docker_containers()
        proxied = [c for c in containers if c["env"].get("DMS_REQUIRE_PROXY", "false").lower() == "true" and "DMS_PROXY_URL" in c["env"]]
        if proxied:
            print("Cannot uninstall: There are currently running containers requiring proxy.")
            for c in proxied:
                print(f"- {c['name']} ({c['env'].get('DMS_PROXY_URL', '')})")
            return
        try:
            subprocess.run(["sudo", "systemctl", "stop", service_name], check=True)
            subprocess.run(["sudo", "systemctl", "disable", service_name], check=True)
            if os.path.exists(service_path):
                subprocess.run(["sudo", "rm", service_path], check=True)
            subprocess.run(["sudo", "systemctl", "daemon-reload"], check=True)
            print(f"Systemd service '{service_name}' stopped and uninstalled.")
        except Exception as e:
            print(f"Failed to uninstall systemd service: {e}")

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
        def install_systemd_service():
            try:
                interval = input("Enter monitor interval in seconds (default 30): ").strip()
                interval = int(interval) if interval else 30
            except Exception:
                interval = 30
            self.install_systemd_service(interval=interval)

        menu_options = {
            "1": ("Show Proxy Manager Log", "📄", self.show_proxy_log),
            "2": ("Install/Update systemd Monitor Service", "🛠", install_systemd_service),
            "3": ("Stop & Uninstall systemd Monitor Service", "🛑", self.uninstall_systemd_service),
        }
        while True:
            print("\n=== Manage Caddy Proxy Manager ===")
            print(f"Status: {self.get_caddy_proxy_status()}")
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
        for c in containers:
            if "proxy_url" in c:  # Only process containers that have a proxy URL
                port = self.get_proxy_port(c)
                ip = c.get('ip_address')
                if ip:
                    caddyfile += f"{c['proxy_url']} {{\n  reverse_proxy {ip}:{port}\n}}\n\n"
                else:
                    # fallback to name (shouldn't happen if IP is always present)
                    caddyfile += f"{c['proxy_url']} {{\n  reverse_proxy {c['name']}:{port}\n}}\n\n"
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