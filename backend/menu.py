#!/usr/bin/env python3

"""
NuNet Appliance Management System - Main Menu
"""

import sys
import subprocess
import os
from pathlib import Path
from typing import Dict, Any
import json
import time
import qrcode
from modules.utils import (
    Colors, ConfigManager, clear_screen, pause,
    format_status, print_header, print_menu_option,
    get_current_branch, get_local_ip, get_public_ip, get_appliance_version, get_ssh_status
)
from modules.dms_manager import DMSManager
from modules.docker_manager import DockerManager
from modules.ensemble_manager import EnsembleManager
from modules.depin_manager import DePINManager, AukiRelayConfig
from modules.organization_manager import OrganizationManager
from modules.log_viewer import LogViewer
from modules.appliance_manager import ApplianceManager
from modules.dms_utils import display_peer_info, get_dms_status_info
from modules.ensemble_manager_v2 import EnsembleManagerV2
from modules.caddy_proxy_manager import CaddyProxyManager
from modules.ddns_manager import DDNSManager
from modules.onboarding_manager import OnboardingManager
from modules.web_manager import WebManager
from modules.system_status import get_system_status
from modules.systemd_helper import systemd_helper

class NuNetMenu:
    def __init__(self):
        """Initialize the NuNet menu"""
        self.status = {}
        self.appliance_manager = ApplianceManager()
        self.ensemble_manager = EnsembleManager()
        self.ensemble_manager_v2 = EnsembleManagerV2()
        self.dms_manager = DMSManager()
        self.organization_manager = OrganizationManager()
        self.depin_manager = DePINManager()
        self.docker_manager = DockerManager()
        self.log_viewer = LogViewer()
        self.config_manager = ConfigManager()
        self.caddy_proxy_manager = CaddyProxyManager()
        self.ddns_manager = DDNSManager()
        self.onboarding_manager = OnboardingManager()
        self.web_manager = None
        self._load_status()

    def _load_status(self):
        """Load the current status of various components"""
        # Load config first
        stored_config = self.config_manager.load_config()
        
        # Initialize status with stored values or defaults
        self.status = {
            'menu_version': self.appliance_manager.get_current_version(),
            'current_branch': get_current_branch(),
            'docker_status': 'Unknown',
            # Initialize DMS status with stored values
            'dms_context': stored_config.get('dms_context', 'Unknown'),
            'dms_did': stored_config.get('dms_did', 'Unknown'),
            'dms_peer_id': stored_config.get('dms_peer_id', 'Unknown'),
            'dms_is_relayed': stored_config.get('dms_is_relayed', None),
            'dms_status': 'Unknown',
            'dms_version': 'Unknown',
            'dms_running': 'Not Running'
        }

        # Quick check for Docker status - non-blocking
        try:
            docker_status = self.docker_manager.check_docker_status()
            self.status['docker_status'] = format_status(docker_status['status'])
        except:
            pass

        # Update DMS status
        try:
            dms_status = self.dms_manager.update_dms_status()
            self.status.update(dms_status)
            self.config_manager.save_config(self.status)
        except Exception:
            pass  # Keep default values if update fails

        # After other status loads:
        unattended = self.appliance_manager.get_unattended_upgrades_status()
        self.status['unattended_enabled'] = unattended['enabled']
        self.status['unattended_last_run'] = unattended['last_run']
        self.status['unattended_last_log'] = unattended['last_log']

    def show_header(self):
        """Display the menu header with current status"""
        clear_screen()
        self.status = get_system_status()
        print(f"{Colors.CYAN}", end='')
        print(r"""::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::
:+#-+#*:::::::::::#+:::%+::::::::::::::@-::+@@@@@%=:::::::-%@@-:::=%@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@=
:+*:::-%=:::::::::#+:::%+::::::::::::::@-::+@@*=%@@%::::::-%@@-::#@@@=:::::::::::::::::::*@@+:::::::
:+*:::::+#::::::::#+:::%+::::::::::::::@-::+@@*::+@@@+::::-%@@-:-@@%:::::::::::::::::::::*@@+:::::::
:+*::::::-%=::::::#+:::%+::::::::::::::@-::+@@*:::-%@@#:::-%@@-:=@@@@@@@@@@@@@@@@@+::::::*@@+:::::::
:+*::::::::+*:::::#+:::#*:::::::::::::-@:::+@@*:::::*@@@=:-%@@-:-@@@:::::::::::::::::::::*@@+:::::::
:+*:::::::::-%=:::#+::::%-::::::::::::#=:::+@@*::::::-%@@%#@@@-::+@@@#+============::::::*@@+:::::::
:+*:::::::::::=#*+%+:::::*%*+=====+*#*-::::+@@*::::::::-#@@@@@-:::-#@@@@@@@@@@@@@@#::::::*@@+:::::::
::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::""")
        print(f"{Colors.NC}")
        print()
        # Don't clear screen again, just print the title and separator
        print(f"\n{Colors.CYAN}🌟 NuNet Appliance Management Menu{Colors.NC}")
        print("=" * 70)
        print(f"Local IP Address: {Colors.MAGENTA}{get_local_ip()}{Colors.NC} Internet IP Address: {Colors.MAGENTA}{get_public_ip()}{Colors.NC}")
        print(f"Appliance Version: {Colors.BLUE}{get_appliance_version()}{Colors.NC} Branch: {Colors.BLUE}{self.status['current_branch']}{Colors.NC} Menu Version: {Colors.BLUE}{self.status['menu_version']}{Colors.NC}")
        unattended_status = (
            f"{Colors.GREEN}Enabled{Colors.NC}" if self.status.get('unattended_enabled')
            else f"{Colors.RED}Disabled{Colors.NC}" if self.status.get('unattended_enabled') is False
            else "Unknown"
        )
        print(f"Automatic Security Updates: {unattended_status} (Last: {self.status.get('unattended_last_run', 'Never')})")
        print(f"Docker Status: {self.status['docker_status']} SSH Status: {get_ssh_status()}")
        # Show Caddy Proxy Status based on systemd service
        caddy_status = self.caddy_proxy_manager.get_caddy_proxy_status()
        print(f"Caddy Proxy Status: {caddy_status}")
        print("=" * 70)
        print(f"DMS Status: {self.status['dms_status']} (v{self.status['dms_version']}) {self.status['dms_running']} Context: {Colors.YELLOW}{self.status['dms_context']}{Colors.NC} ")
        if self.status['dms_peer_id'] != 'Unknown':
            print(f"DMS DID: {Colors.YELLOW}{self.status['dms_did']}{Colors.NC}")
            print(f"DMS Peer ID: {Colors.CYAN}{self.status['dms_peer_id']}{Colors.NC}")
            if self.status['dms_is_relayed'] is not None:
                relay_status = "Using relay" if self.status['dms_is_relayed'] else "Direct connection"
                relay_color = Colors.YELLOW if self.status['dms_is_relayed'] else Colors.GREEN
                print(f"NuNet Network Connection Type: {relay_color}{relay_status}{Colors.NC}")
        print("=" * 70) 

    def update_status(self):
        """Update system status"""
        self._load_status()
        self.config_manager.save_config(self.status)

    def _handle_dms_action(self, action_func):
        result = action_func()
        print(result['message'])
        status = get_dms_status_info()
        self.status.update(status)
        self.config_manager.save_config(self.status)

    def manage_dms_menu(self):
        """DMS Management submenu (lambda refactor)"""
        menu_options = {
            "1": ("Start / Restart DMS", "⚡", lambda: self._handle_dms_action(self.dms_manager.restart_dms)),
            "2": ("Stop DMS", "⚡", lambda: print(self.dms_manager.stop_dms()['message'])),
            "3": ("Enable DMS", "⚡", lambda: print(self.dms_manager.enable_dms()['message'])),
            "4": ("Disable DMS", "⚡", lambda: print(self.dms_manager.disable_dms()['message'])),
            "5": ("Initialize DMS", "⚡", lambda: self._handle_dms_action(self.dms_manager.initialize_dms)),
            "6": ("Onboard Compute", "⚡", lambda: print(self.dms_manager.onboard_compute()['message'])),
            "7": ("Offboard Compute", "⚡", lambda: print(self.dms_manager.offboard_compute()['message'])),
            "8": ("Current Resource Allocation", "⚡", lambda: print(self.dms_manager.get_resource_allocation()['message'])),
            "9": ("View Connected Peers", "👥", lambda: (
                print("\n=== Connected Peers ==="),
                print(self.dms_manager.view_peer_details()['message'])
            )),
            "10": ("View Self Peer Info", "🔍", lambda: display_peer_info(self.dms_manager.get_self_peer_info(), Colors)),
            "11": ("Update DMS To Latest Version", "⬇️", lambda: print(self.dms_manager.update_dms()['message'])),
            "12": ("View Full DMS Status", "📊", self.dms_manager.show_full_status),

        }

        while True:
            print_header("Manage NuNet DMS")
            for key, (label, icon, _) in menu_options.items():
                print_menu_option(key, label, icon)
            print_menu_option("0", "Return to Main Menu", "🔙")
            print()

            choice = input("Select an option: ")
            if choice == "0":
                break
            elif choice in menu_options:
                menu_options[choice][2]()  # Call the lambda/action
            else:
                print(f"{Colors.RED}Invalid option!{Colors.NC}")

            pause()
            self.update_status()

    def manage_ensembles_menu(self):
        """Ensemble Management submenu"""
        menu_options = {
            "1": ("View Running Ensembles", "⚡", lambda: print(self.ensemble_manager.view_running_ensembles()['message'])),
            "2": ("Deploy an Ensemble", "⚡", lambda: self.ensemble_manager.deploy_ensemble_menu()),
            "3": ("Manage Templates", "⚡", lambda: self.ensemble_manager.manage_ensemble_templates_menu()),
            "4": ("Download Example Templates", "⚡", lambda: print(self.ensemble_manager.download_example_ensembles_menu()['message'])),
        }
        while True:
            print_header("Manage Ensembles")
            for key, (label, icon, _) in menu_options.items():
                print_menu_option(key, label, icon)
            print_menu_option("0", "Return to Main Menu", "🔙")
            print()
            choice = input("Select an option: ")
            if choice == "0":
                break
            elif choice in menu_options:
                menu_options[choice][2]()
            else:
                print(f"{Colors.RED}Invalid option!{Colors.NC}")
            pause()

    def manage_depin_menu(self):
        menu_options = {
            "1": ("Deploy AUKI Relay Node", "⚡", self.depin_manager.deploy_auki_relay_interactive),
            "2": ("Deploy Another DePIN Node (Future)", "📡", lambda: print("🚧 Future feature: Deploy another DePIN node")),
        }
        while True:
            print_header("Deploy DePIN Nodes Locally")
            for key, (label, icon, _) in menu_options.items():
                print_menu_option(key, label, icon)
            print_menu_option("0", "Return to Main Menu", "🔙")
            print()
            choice = input("Select an option: ")
            if choice == "0":
                break
            elif choice in menu_options:
                menu_options[choice][2]()
            else:
                print(f"{Colors.RED}Invalid option!{Colors.NC}")
            pause()

    def manage_organizations_menu(self):
        menu_options = {
            "1": ("Join NuNet Compute Testnet", "⚡", lambda: self.organization_manager.join_nunet_network()),
            "2": ("Connect to a Custom Organization (Future)", "🔗", lambda: print("🚧 Future feature: Connect to a Custom Organization")),
            "3": ("View Your Safe & Joined Organisations", "⚡", lambda: self.organization_manager.view_capability_relationships()),
        }
        while True:
            print_header("Connecting to Organizations")
            for key, (label, icon, _) in menu_options.items():
                print_menu_option(key, label, icon)
            print_menu_option("0", "Return to Main Menu", "🔙")
            print()
            choice = input("Select an option: ")
            if choice == "0":
                break
            elif choice in menu_options:
                menu_options[choice][2]()
            else:
                print(f"{Colors.RED}Invalid option!{Colors.NC}")
            pause()

    def view_logs_menu(self):
        menu_options = {
            "1": ("View DMS Log", "⚡", self.log_viewer.view_dms_log),
            "2": ("View Deployments History", "⚡", self.log_viewer.view_deployments_log),
        }
        while True:
            print_header("View Logfiles")
            for key, (label, icon, _) in menu_options.items():
                print_menu_option(key, label, icon)
            print_menu_option("0", "Return to Main Menu", "🔙")
            print()
            choice = input("Select an option: ")
            if choice == "0":
                break
            elif choice in menu_options:
                result = menu_options[choice][2]()
                if result['status'] == "error":
                    print(f"{Colors.RED}{result['message']}{Colors.NC}")
                    pause()
            else:
                print(f"{Colors.RED}Invalid option!{Colors.NC}")
                pause()

    def manage_appliance_menu(self):
        menu_options = {
            "1": ("Change active branch", "🔄", lambda: self.appliance_manager.change_branch_interactive()),
            "2": ("Check for and install appliance updates", "⚡", lambda: self.appliance_manager.check_and_update_appliance_interactive()),
            "3": ("Re-download menu", "⚡", lambda: self.appliance_manager.redownload_menu_interactive()),
            "4": ("Manage plugins", "⚡", lambda: print(self.appliance_manager.manage_plugins().get('message', 'No message returned.'))),
            "5": ("Backup appliance", "⚡", lambda: print(self.appliance_manager.backup_appliance().get('message', 'No message returned.'))),
            "6": ("Restore from backup", "⚡", lambda: self._handle_restore_backup()),
            "7": ("Enable SSH Access", "⚡", lambda: self.appliance_manager.enable_ssh_access()),
            "8": ("Run Manual OS Updates", "⬆️", lambda: self.appliance_manager.run_os_updates_interactive()),
            "9": ("Enable Automatic Security Updates", "🟢", lambda: self.appliance_manager.enable_unattended_upgrades()),
            "10": ("Disable Automatic Security Updates", "🛑", lambda: self.appliance_manager.disable_unattended_upgrades()),
            "11": ("Manage Caddy Proxy", "🌐", lambda: self.caddy_proxy_manager.show_manager_menu()),
            "12": ("Manage DDNS", "🌍", lambda: self._show_ddns_menu()),
            "13": ("Update Known Organizations", "🏢", lambda: self.appliance_manager.check_and_update_known_organizations_interactive()),

        }
        while True:
            print_header("🔗 Manage NuNet Appliance")
            current_branch = get_current_branch()
            print(f"Current branch: {Colors.GREEN}{current_branch}{Colors.NC}")
            print()
            for key, (label, icon, _) in menu_options.items():
                print_menu_option(key, label, icon)
            print_menu_option("0", "Return to Main Menu", "🔙")
            print()
            choice = input("Select an option: ")
            if choice == "0":
                break
            elif choice in menu_options:
                menu_options[choice][2]()
            else:
                print(f"{Colors.RED}Invalid option!{Colors.NC}")
            pause()
            self.update_status()

    def _handle_restore_backup(self):
        # Implementation of _handle_restore_backup method
        pass

    def manage_ensembles_v2_menu(self):
        """Enhanced Ensemble Management submenu (V2, lambda style, robust message printing)"""
        while True:
            print_header("Enhanced Ensemble Manager (Beta)")
            result = self.ensemble_manager_v2.view_running_ensembles()
            print(result["message"])

            # Show help message if enabled
            if self.ensemble_manager_v2.show_help_message:
                self.ensemble_manager_v2.show_help()

            menu_options = {
                "1": ("Select an ensemble", "🎯", lambda: self.ensemble_manager_v2.handle_ensemble_selection(result)),
                "2": ("Deploy new ensemble", "🚀", self.ensemble_manager_v2.deploy_ensemble_menu),
                "3": ("Refresh list", "🔄", lambda: None),
                "4": ("Edit an ensemble template", "✏️", self.ensemble_manager_v2.edit_ensemble_menu),
                "5": ("Copy an ensemble template", "📄", self.ensemble_manager_v2.copy_ensemble_menu),
                "6": ("Delete an ensemble template", "🗑️", self.ensemble_manager_v2.delete_ensemble_menu),
                "7": ("Download example ensembles", "⬇️", self.ensemble_manager_v2.download_examples_menu),
                "8": ("Toggle Help", "❓", self.ensemble_manager_v2.toggle_help),
            }

            print("\nOptions:")
            for key, (label, icon, _) in menu_options.items():
                print_menu_option(key, label, icon)
            print_menu_option("0", "Return to Main Menu", "🔙")
            choice = input("\nSelect an option: ")
            if choice == "0":
                break
            elif choice in menu_options:
                action_result = menu_options[choice][2]()
                # Print the message if the action returns a dict with a "message" key
                if isinstance(action_result, dict) and "message" in action_result:
                    print(action_result["message"])
                    pause()
                elif action_result == "exit":
                    break
                # For actions that print their own output (like menus), do nothing
            else:
                print(f"{Colors.RED}Invalid option!{Colors.NC}")
                pause()

    def _show_ddns_menu(self):
        """Show DDNS management menu"""
        while True:
            clear_screen()
            print_header("DDNS Management")
            print("\n1) 📋 List DDNS-enabled containers")
            print("2) 🔄 Force DDNS update for container")
            print("3) ⚙️  Set DDNS API server address")
            print("0) 🔙 Return to Appliance Menu")
            
            choice = input("\nSelect an option: ")
            
            if choice == "0":
                break
            elif choice == "1":
                result = self.ddns_manager.list_ddns_containers()
                print(result["message"])
                pause()
            elif choice == "2":
                result = self.ddns_manager.force_ddns_update()
                if result["status"] == "menu":
                    print(result["message"])
                    for i, container in enumerate(result["containers"], 1):
                        print(f"{i}) {container['name']}")
                    print("0) Cancel")
                    
                    try:
                        choice = int(input("\nSelect container number: "))
                        if choice == 0:
                            continue
                        if 1 <= choice <= len(result["containers"]):
                            container = result["containers"][choice - 1]
                            update_result = self.ddns_manager.force_ddns_update(container["name"])
                            print(f"\n{update_result['message']}")
                        else:
                            print("Invalid selection!")
                    except ValueError:
                        print("Invalid input!")
                else:
                    print(result["message"])
                pause()
            elif choice == "3":
                # Set DDNS API server address
                config_path = Path.home() / "nunet" / "appliance" / "ddns-client" / "ddns-config.json"
                current = getattr(self.ddns_manager, 'api_server', 'https://api.parallelvector.com:8080')
                print(f"Current DDNS API server: {current}")
                new_addr = input("Enter new DDNS API server address (e.g. https://api.parallelvector.com:8080): ").strip()
                if new_addr:
                    # Write to config file
                    config_path.parent.mkdir(parents=True, exist_ok=True)
                    config = {"ddns_api_server": new_addr}
                    with open(config_path, "w") as f:
                        json.dump(config, f, indent=2)
                    # Reload in manager
                    self.ddns_manager.api_server = new_addr
                    print(f"DDNS API server updated to: {new_addr}")
                else:
                    print("No change made.")
                pause()
            else:
                print("Invalid option!")
                pause()

    def manage_web_manager_menu(self):
        """Simplified Web Manager Management submenu"""
        menu_options = {
            "1": ("Start Web Manager Service", "🚀", lambda: print(f"Service started: {systemd_helper.start('nunet-web-manager.service')}")),
            "2": ("Stop Web Manager Service", "⏹", lambda: print(f"Service stopped: {systemd_helper.stop('nunet-web-manager.service')}")),
            "3": ("Restart Web Manager Service", "🔄", lambda: print(f"Service restarted: {systemd_helper.restart('nunet-web-manager.service')}")),
            "4": ("Enable Web Manager Service", "✅", lambda: print(f"Service enabled: {systemd_helper.enable('nunet-web-manager.service')}")),
            "5": ("Disable Web Manager Service", "❌", lambda: print(f"Service disabled: {systemd_helper.disable('nunet-web-manager.service')}")),
            "6": ("Show Service Status", "📊", lambda: self._show_web_manager_status()),
            "7": ("Show QR Code", "📱", lambda: self._show_web_manager_qr()),
            "8": ("Show Service Logs", "📄", lambda: self._show_web_manager_logs()),
        }

        while True:
            print_header("Manage Web Manager Service")
            for key, (label, icon, _) in menu_options.items():
                print_menu_option(key, label, icon)
            print_menu_option("0", "Return to Main Menu", "🔙")
            print()

            choice = input("Select an option: ")
            if choice == "0":
                break
            elif choice in menu_options:
                menu_options[choice][2]()  # Call the lambda/action
            else:
                print(f"{Colors.RED}Invalid option!{Colors.NC}")

            pause()

    def _show_web_manager_status(self):
        """Show web manager service status"""
        status = systemd_helper.get_status('nunet-web-manager.service')
        
        print(f"\nService Status:")
        print(f"  Active: {'✅' if systemd_helper.is_active('nunet-web-manager.service') else '❌'}")
        print(f"  Enabled: {'✅' if systemd_helper.is_enabled('nunet-web-manager.service') else '❌'}")
        
        if status:
            print(f"  State: {status.get('ActiveState', 'Unknown')}")
            print(f"  Load State: {status.get('LoadState', 'Unknown')}")
            print(f"  Unit File State: {status.get('UnitFileState', 'Unknown')}")

    def _show_web_manager_qr(self):
        """Show web manager QR code"""
        try:
            # Check if service is running
            if not systemd_helper.is_active('nunet-web-manager.service'):
                print("❌ Web manager service is not running")
                return
            
            # Get local IP address
            import socket
            hostname = socket.gethostname()
            local_ip = socket.gethostbyname(hostname)
            url = f"https://{local_ip}:8080"
            
            # Try to get password from config
            config_file = Path.home() / ".config" / "nunet" / "web_manager_config.json"
            password = "setup-password"
            
            if config_file.exists():
                try:
                    import json
                    with open(config_file, 'r') as f:
                        config = json.load(f)
                        password = config.get('password', 'setup-password')
                except Exception:
                    pass
            
            # Generate QR code
            import qrcode
            qr_data = f"{url}?password={password}"
            qr = qrcode.QRCode(border=2)
            qr.add_data(qr_data)
            qr.make()
            
            # Display QR code
            matrix = qr.get_matrix()
            print("\n📱 Web Manager QR Code:")
            for row in matrix:
                print(''.join('██' if cell else '  ' for cell in row))
            print(f"\n🌐 Or visit manually: {url}")
            print(f"🔑 Setup Password: {password}")
            
        except Exception as e:
            print(f"❌ Error generating QR code: {e}")

    def _show_web_manager_logs(self):
        """Show web manager service logs"""
        logs = systemd_helper.get_logs('nunet-web-manager.service', 20)
        if logs:
            print("\n📄 Recent Web Manager Service Logs:")
            print("=" * 50)
            for log in logs[-20:]:  # Show last 20 lines
                print(log)
        else:
            print("❌ No logs available or service not running.")

    def manage_onboarding_service_menu(self):
        """Onboarding Service Management submenu"""
        menu_options = {
            "1": ("Start Onboarding Service", "🚀", lambda: print(systemd_helper.start("nunet-onboarding.service"))),
            "2": ("Stop Onboarding Service", "⏹", lambda: print(systemd_helper.stop("nunet-onboarding.service"))),
            "3": ("Restart Onboarding Service", "🔄", lambda: print(systemd_helper.restart("nunet-onboarding.service"))),
            "4": ("Enable Onboarding Service", "✅", lambda: print(systemd_helper.enable("nunet-onboarding.service"))),
            "5": ("Disable Onboarding Service", "❌", lambda: print(systemd_helper.disable("nunet-onboarding.service"))),
            "6": ("Show Onboarding Status", "📊", lambda: self._show_onboarding_status()),
            "7": ("Show Service Logs", "📄", lambda: self._show_onboarding_service_logs()),
            "8": ("Reset Onboarding State", "🔄", lambda: self._reset_onboarding_state()),
        }

        while True:
            print_header("Manage Onboarding Service")
            for key, (label, icon, _) in menu_options.items():
                print_menu_option(key, label, icon)
            print_menu_option("0", "Return to Main Menu", "🔙")
            print()

            choice = input("Select an option: ")
            if choice == "0":
                break
            elif choice in menu_options:
                menu_options[choice][2]()  # Call the lambda/action
            else:
                print(f"{Colors.RED}Invalid option!{Colors.NC}")

            pause()

    def _show_onboarding_service_logs(self):
        """Show onboarding service logs"""
        logs = systemd_helper.get_logs("nunet-onboarding.service", 20)
        if logs:
            print("\n📄 Recent Onboarding Service Logs:")
            print("=" * 50)
            for log in logs[-20:]:  # Show last 20 lines
                print(log)
        else:
            print("❌ No logs available or service not running.")

    def _reset_onboarding_state(self):
        """Reset onboarding state"""
        print("⚠️  This will reset the onboarding state and allow you to run onboarding again.")
        print("This action cannot be undone.")
        if input("Are you sure you want to reset onboarding state? (y/N): ").lower() == 'y':
            mgr = OnboardingManager()
            mgr.clear_state()
            print("✅ Onboarding state reset successfully")
        else:
            print("Reset cancelled")

    def _show_onboarding_status(self):
        mgr = OnboardingManager()
        status = mgr.get_onboarding_status()
        print("\nOnboarding Status:")
        for k, v in status.items():
            print(f"  {k}: {v}")
        print(f"DMS Ready: {mgr.check_dms_ready()}")

    def main_menu(self):
        menu_options = {
            "1": ("Manage NuNet DMS", "🔄", lambda: self.manage_dms_menu()),
            "2": ("Manage Ensembles", "📜", lambda: self.manage_ensembles_menu()),
            "20": ("Enhanced Ensemble Manager (Beta)", "🧪", lambda: self.manage_ensembles_v2_menu()),
            "3": ("View Peer Details", "🔎", lambda: print(self.dms_manager.view_peer_details()['message'])),
            "4": ("Run DePIN Nodes Locally", "🛠", lambda: self.manage_depin_menu()),
            "5": ("Connect to Organizations", "🔗", lambda: self.manage_organizations_menu()),
            "6": ("View Logfiles", "📄", lambda: self.view_logs_menu()),
            "7": ("View Locally Running Containers", "🐳", lambda: self.docker_manager.view_docker_containers()),
            "8": ("Manage NuNet Appliance", "🐳", lambda: self.manage_appliance_menu()),
            "10": ("Manually Update System Status", "🔄", lambda: self._handle_manual_status_update()),
            "12": ("Restart Menu", "🔄", lambda: self.restart_menu()),
            "14": ("Manage Web Manager Service", "🌐", lambda: self.manage_web_manager_menu()),
            "15": ("Manage Onboarding Service", "🚀", lambda: self.manage_onboarding_service_menu()),
            "99": ("Web Onboarding", "🚀", self._handle_full_onboarding),
        }

        while True:
            self.show_header()
            for key, (label, icon, _) in menu_options.items():
                print_menu_option(key, label, icon)
            print_menu_option("0", "Exit", "❌")
            print()

            try:
                choice = input("Select an option: ")
                if choice == "0":
                    print(f"{Colors.RED}Exiting...{Colors.NC}")
                    sys.exit(0)
                elif choice in menu_options:
                    menu_options[choice][2]()
                else:
                    print(f"{Colors.RED}Invalid option!{Colors.NC}")
                    pause()
                self.update_status()
            except KeyboardInterrupt:
                print(f"\n{Colors.RED}Operation cancelled by user{Colors.NC}")
                pause()
                continue

    def _handle_manual_status_update(self):
        self.update_status()
        print(f"{Colors.GREEN}Status updated successfully{Colors.NC}")
        pause()

    def restart_menu(self):
        print("Restarting menu...")
        python = sys.executable
        os.execl(python, python, *sys.argv)

    def _handle_full_onboarding(self):
        """Handle the full device onboarding process"""
        print_header("Full Device Onboarding")
        print("Choose setup method:")
        print("1. Terminal-based setup")
        print("2. Web-based setup")
        
        choice = input("\nSelect setup method (1/2): ")
        
        if choice == "1":
            self._handle_terminal_onboarding()
        elif choice == "2":
            self._handle_web_onboarding()
        else:
            print("Invalid choice!")
            return

    def _handle_terminal_onboarding(self):
        """Handle terminal-based onboarding"""
        print("\nThis will perform the following steps:")
        print("1. Update DMS to latest version")
        print("2. Restart DMS")
        print("3. Generate wormhole code for organization joining")
        print("4. Install Proxy and DDNS support")
        print("\nNote: You will need to provide the generated wormhole code to your organization administrator.")
        if input("\nDo you want to proceed? (y/N): ").lower() != 'y':
            print("Onboarding cancelled.")
            return
        print("\nStarting onboarding process...")
        # Start the onboarding systemd service if not running
        def is_service_active():
            result = subprocess.run(["systemctl", "is-active", "nunet-onboarding.service"], capture_output=True, text=True)
            return result.stdout.strip() == "active"
        if not is_service_active():
            self.onboarding_manager.install_systemd_service()
        # Poll the state file for progress
        last_step = None
        while True:
            state = self.onboarding_manager.get_onboarding_status()
            step = state.get('step')
            progress = state.get('progress', 0)
            status = state.get('status')
            wormhole_code = state.get('wormhole_code')
            error = state.get('error')
            if step != last_step:
                print(f"Step: {step} (Progress: {progress}%)")
                last_step = step
            if wormhole_code:
                print(f"\nIMPORTANT: Please provide this wormhole code to your organization administrator:")
                print(wormhole_code)
            if error:
                print(f"\nOnboarding failed: {error}")
                break
            if status == 'complete':
                print("\nOnboarding completed successfully!")
                break
            time.sleep(5)
        pause()
        self.update_status()

    def _handle_web_onboarding(self):
        """Handle web-based onboarding"""
        try:
            # Initialize web manager
            self.web_manager = WebManager(self.onboarding_manager)

            # Install the onboarding systemd service if not running
            def is_service_active():
                result = subprocess.run(["systemctl", "is-active", "nunet-onboarding.service"], capture_output=True, text=True)
                return result.stdout.strip() == "active"
            
            if not is_service_active():
                print("\nInstalling onboarding service...")
                self.onboarding_manager.install_systemd_service()
                print("Onboarding service installed and started.")
            
            
            # Generate setup password
            password = self.web_manager.generate_setup_password()
            
            # Get server info
            server_info = self.web_manager.get_server_info()
            
            print("\nStarting web-based setup...")
            # Generate and print square QR code with side-by-side text
            qr_data = f"{server_info['url']}?password={password}"
            print(f"DEBUG: QR data is: {qr_data}")
            qr = qrcode.QRCode(border=2)
            qr.add_data(qr_data)
            qr.make()
            matrix = qr.get_matrix()
            qr_lines = [''.join('██' if cell else '  ' for cell in row) for row in matrix]
            text_lines = [
                "Scan this QR code to open the onboarding wizard on your phone:",
                "",
                f"{Colors.GREEN}Or visit this URL in your web browser:{Colors.NC}",
                f"{Colors.CYAN}{server_info['url']}{Colors.NC}",
                "",
                f"{Colors.YELLOW}Setup Password:{Colors.NC}",
                f"{Colors.CYAN}{password}{Colors.NC}",
                "",
                f"{Colors.YELLOW}Note:{Colors.NC}",
                "- The password will expire after 30 minutes",
                "- You have 10 login attempts",
                "- The web interface will automatically close after successful onboarding",
                "",
                "Press Ctrl+C to stop the web server and return to the menu"
            ]
            max_qr_height = len(qr_lines)
            max_text_height = len(text_lines)
            total_lines = max(max_qr_height, max_text_height)
            qr_lines += [' ' * len(qr_lines[0])] * (total_lines - max_qr_height)
            text_lines += [''] * (total_lines - max_text_height)
            for qr_line, text_line in zip(qr_lines, text_lines):
                print(f"{qr_line}   {text_line}")
            
            # Start web server
            self.web_manager.start_server()
            
        except KeyboardInterrupt:
            print("\nStopping web server...")
            if self.web_manager:
                self.web_manager.stop_server()
            print("Web server stopped.")
        except Exception as e:
            print(f"\n{Colors.RED}Error: {str(e)}{Colors.NC}")
            if self.web_manager:
                self.web_manager.stop_server()
        finally:
            pause()
            self.update_status()


if __name__ == "__main__":
    menu = NuNetMenu()
    try:
        menu.main_menu()
    except KeyboardInterrupt:
        print(f"\n{Colors.RED}Exiting...{Colors.NC}")
        sys.exit(0) 