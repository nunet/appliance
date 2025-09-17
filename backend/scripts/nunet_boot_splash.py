#!/usr/bin/env python3
"""
NuNet Boot Splash Screen
Combines QR code generation, beautiful display, and server information
Launched via .bashrc for web-based system management
"""

import os
import sys
import json
import socket
import subprocess
import qrcode
import requests
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Tuple

class Colors:
    """ANSI color codes for terminal output"""
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'
    WHITE = '\033[97m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    NC = '\033[0m'  # No Color

class NuNetBootSplash:
    """Enhanced boot splash screen with QR code and server information"""
    
    def __init__(self):
        self.colors = Colors()
        repo_root = Path(__file__).resolve().parents[2]
        self.credentials_file = repo_root / "deploy" / "admin_credentials.json"
        self.onboarding_state = Path.home() / "nunet" / "appliance" / "onboarding_state.json"
        
    def clear_screen(self):
        """Clear the terminal screen"""
        os.system('clear')
        
    def get_nunet_ascii_art(self) -> str:
        """Get NuNet ASCII art logo"""
        return r"""::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::
:+#-+#*:::::::::::#+:::%+::::::::::::::@-::+@@@@@%=:::::::-%@@-:::=%@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@=
:+*:::-%=:::::::::#+:::%+::::::::::::::@-::+@@*=%@@%::::::-%@@-::#@@@=:::::::::::::::::::*@@+:::::::
:+*:::::+#::::::::#+:::%+::::::::::::::@-::+@@*::+@@@+::::-%@@-:-@@%:::::::::::::::::::::*@@+:::::::
:+*::::::-%=::::::#+:::%+::::::::::::::@-::+@@*:::-%@@#:::-%@@-:=@@@@@@@@@@@@@@@@@+::::::*@@+:::::::
:+*::::::::+*:::::#+:::#*:::::::::::::-@:::+@@*:::::*@@@=:-%@@-:-@@@:::::::::::::::::::::*@@+:::::::
:+*:::::::::-%=:::#+::::%-::::::::::::#=:::+@@*::::::-%@@%#@@@-::+@@@#+============::::::*@@+:::::::
:+*:::::::::::=#*+%+:::::*%*+=====+*#*-::::+@@*::::::::-#@@@@@-:::-#@@@@@@@@@@@@@@#::::::*@@+:::::::
::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::::"""
    
    def get_local_ip(self) -> str:
        """Get the local IP address"""
        try:
            # Try to get IP from hostname first
            hostname = socket.gethostname()
            local_ip = socket.gethostbyname(hostname)
            if local_ip and not local_ip.startswith('127.'):
                return local_ip
        except:
            pass
        
        # Fallback: try to get IP from network interfaces
        try:
            result = subprocess.run(['hostname', '-I'], capture_output=True, text=True, check=True)
            ips = result.stdout.strip().split()
            for ip in ips:
                if not ip.startswith('127.') and '.' in ip:
                    return ip
        except:
            pass
        
        return "localhost"
    
    def get_public_ip(self) -> str:
        """Get the public IP address"""
        try:
            result = subprocess.run(['curl', '-s', 'ifconfig.me'], capture_output=True, text=True, timeout=5)
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
        except:
            pass
        return "Unknown"
    
    def get_admin_password_status(self) -> Tuple[str, str]:
        """Return admin password status text and color"""
        if not self.credentials_file.exists():
            return ("Pending setup in browser", self.colors.YELLOW)
        try:
            with open(self.credentials_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if data.get('needs_reset'):
                return ("Reset required", self.colors.YELLOW)
            username = data.get('username', 'admin')
            updated_raw = data.get('updated_at') or data.get('created_at')
            if updated_raw:
                try:
                    updated_dt = datetime.fromisoformat(updated_raw)
                    updated_display = updated_dt.strftime('%Y-%m-%d %H:%M')
                except ValueError:
                    updated_display = updated_raw
                return (f"Configured for {username} ({updated_display})", self.colors.GREEN)
            return (f"Configured for {username}", self.colors.GREEN)
        except Exception:
            return ("Configuration unreadable", self.colors.RED)
    
    def check_web_manager_service(self) -> bool:
        """Check if web manager service is running"""
        try:
            result = subprocess.run(['systemctl', 'is-active', 'nunet-appliance-web.service'], 
                                  capture_output=True, text=True)
            return result.stdout.strip() == 'active'
        except:
            return False
    
    def get_system_info(self) -> Dict[str, str]:
        """Get basic system information"""
        info = {}
        
        # Hostname
        try:
            info['hostname'] = socket.gethostname()
        except:
            info['hostname'] = "Unknown"
        
        # Uptime
        try:
            result = subprocess.run(['uptime', '-p'], capture_output=True, text=True)
            info['uptime'] = result.stdout.strip() if result.returncode == 0 else "Unknown"
        except:
            info['uptime'] = "Unknown"
        
        # Memory usage
        try:
            result = subprocess.run(['free', '-h'], capture_output=True, text=True)
            if result.returncode == 0:
                lines = result.stdout.strip().split('\n')
                if len(lines) > 1:
                    mem_line = lines[1].split()
                    if len(mem_line) >= 3:
                        info['memory'] = f"{mem_line[2]}/{mem_line[1]} used"
            else:
                info['memory'] = "Unknown"
        except:
            info['memory'] = "Unknown"
        
        # Disk usage
        try:
            result = subprocess.run(['df', '-h', '/'], capture_output=True, text=True)
            if result.returncode == 0:
                lines = result.stdout.strip().split('\n')
                if len(lines) > 1:
                    disk_line = lines[1].split()
                    if len(disk_line) >= 5:
                        info['disk'] = f"{disk_line[4]} used"
            else:
                info['disk'] = "Unknown"
        except:
            info['disk'] = "Unknown"
        
        # DMS status
        try:
            result = subprocess.run(['systemctl', 'is-active', 'nunetdms.service'], 
                                  capture_output=True, text=True)
            dms_status = result.stdout.strip()
            if dms_status == 'active':
                info['dms_status'] = f"{self.colors.GREEN}Running{self.colors.NC}"
            else:
                info['dms_status'] = f"{self.colors.RED}Stopped{self.colors.NC}"
        except:
            info['dms_status'] = f"{self.colors.YELLOW}Unknown{self.colors.NC}"
        
        return info
    
    def generate_qr_code(self, url: str) -> list:
        """Generate QR code matrix"""
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=1,
            border=2,
        )
        qr.add_data(url)
        qr.make(fit=True)
        return qr.get_matrix()
    
    def display_side_by_side(self, qr_lines: list, text_lines: list):
        """Display QR code and text side by side"""
        max_qr_height = len(qr_lines)
        max_text_height = len(text_lines)
        total_lines = max(max_qr_height, max_text_height)
        
        # Pad arrays to same length
        if qr_lines:
            qr_width = len(qr_lines[0]) if qr_lines else 0
            qr_lines += [' ' * qr_width] * (total_lines - max_qr_height)
        text_lines += [''] * (total_lines - max_text_height)
        
        # Display side by side
        for qr_line, text_line in zip(qr_lines, text_lines):
            print(f"{qr_line}   {text_line}")
    
    def show_boot_splash(self):
        """Main method to display the boot splash screen"""
        # Clear screen
        self.clear_screen()
        
        # Display header
        print(f"{self.colors.CYAN}{self.get_nunet_ascii_art()}{self.colors.NC}")
        print()
        print(f"{self.colors.YELLOW}{self.colors.BOLD}NUNET APPLIANCE - WEB MANAGEMENT ACCESS{self.colors.NC}")
        print()
        
        # Get connection information
        local_ip = self.get_local_ip()
        public_ip = self.get_public_ip()
        password_status, password_color = self.get_admin_password_status()
        url = f"http://{local_ip}:8080"
        
        # Check service status
        web_service_running = self.check_web_manager_service()
        
        # Get system information
        system_info = self.get_system_info()
        
        # Generate QR code
        try:
            qr_matrix = self.generate_qr_code(url)
            qr_lines = [''.join('██' if cell else '  ' for cell in row) for row in qr_matrix]
        except ImportError:
            qr_lines = [
                "QR Code generation requires",
                "python3-qrcode package.",
                "Install with:",
                "sudo apt install python3-qrcode"
            ]
        except Exception as e:
            qr_lines = [f"QR Code Error: {str(e)}"]
        
        # Create information text with utilization data
        text_lines = [
            f"{self.colors.GREEN}Scan QR Code{self.colors.NC}",
            "",
            f"{self.colors.CYAN}URL: {url}{self.colors.NC}",
            f"{self.colors.MAGENTA}Admin Password: {self.colors.NC} {password_color}{password_status}{self.colors.NC}",
            "",
            f"{self.colors.YELLOW}Host: {system_info.get('hostname', 'Unknown')} | {local_ip}{self.colors.NC}",
            f"Public IP: {public_ip}",
            f"DMS: {system_info.get('dms_status', 'Unknown')} | Web: {'OK' if web_service_running else 'Down'}",
            f"Uptime: {system_info.get('uptime', 'Unknown')}",
            f"Memory: {system_info.get('memory', 'Unknown')}",
            f"Disk: {system_info.get('disk', 'Unknown')}",
            "",
            f"{self.colors.BLUE}Quick Actions:{self.colors.NC}",
            f"{self.colors.WHITE}1{self.colors.NC} Update Organizations",
            f"{self.colors.WHITE}2{self.colors.NC} Reset Admin Password",
            f"{self.colors.WHITE}3{self.colors.NC} Enable SSH Access",
            f"{self.colors.WHITE}4{self.colors.NC} Quit to Terminal",
            "",
            f"{self.colors.CYAN}Scan the QR code or open the URL above{self.colors.NC}",
            f"{self.colors.MAGENTA}Time: {datetime.now().strftime('%H:%M:%S')}{self.colors.NC}"
        ]
        # Display side by side
        self.display_side_by_side(qr_lines, text_lines)
        
        # Handle user input
        try:
            choice = input().strip()
            self.handle_user_choice(choice, web_service_running)
        except KeyboardInterrupt:
            print(f"\n{self.colors.YELLOW}Exiting...{self.colors.NC}")
            return
    
    def handle_user_choice(self, choice: str, web_service_running: bool):
        """Handle user menu choices"""
        if choice == "1":
            self.update_organizations_ensembles()
        elif choice == "2":
            self.reset_password()
        elif choice == "3":
            self.enable_ssh()
        elif choice == "4":
            print(f"{self.colors.YELLOW}Quitting to terminal...{self.colors.NC}")
            return
        elif choice == "":
            print(f"{self.colors.BLUE}Continuing to shell...{self.colors.NC}")
            return
        else:
            print(f"{self.colors.RED}Invalid choice. Continuing to shell...{self.colors.NC}")
            return
    
    def update_organizations_ensembles(self):
        """Update organizations"""
        print(f"\n{self.colors.YELLOW} Updating Organizations...{self.colors.NC}")
        
        # Update Organizations
        try:
            # Download known organizations from GitLab
            url = "https://gitlab.com/nunet/solutions/nunet-appliance/-/raw/main/config/known_orgs/known_organizations.json"
            print(f"{self.colors.CYAN} Downloading organizations from GitLab...{self.colors.NC}")
            
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            
            # Parse JSON to validate it
            orgs_data = response.json()
            print(f"{self.colors.GREEN} Downloaded {len(orgs_data)} organizations{self.colors.NC}")
            
            # Create target directory if it doesn't exist
            target_dir = Path.home() / "nunet" / "appliance" / "known_orgs"
            target_dir.mkdir(parents=True, exist_ok=True)
            
            # Write to local file
            target_file = target_dir / "known_organizations.json"
            with open(target_file, 'w') as f:
                json.dump(orgs_data, f, indent=2)
            
            # Set secure permissions
            target_file.chmod(0o644)
            
            print(f"{self.colors.GREEN} Organizations updated successfully{self.colors.NC}")
            print(f"{self.colors.CYAN} Saved to: {target_file}{self.colors.NC}")
            
            # Show available organizations
            print(f"\n{self.colors.YELLOW} Available Organizations:{self.colors.NC}")
            for did, org_info in orgs_data.items():
                name = org_info.get('name', 'Unknown')
                print(f"   {name}")
            
        except requests.exceptions.RequestException as e:
            print(f"{self.colors.RED} Network error downloading organizations: {e}{self.colors.NC}")
        except json.JSONDecodeError as e:
            print(f"{self.colors.RED} Error parsing organizations data: {e}{self.colors.NC}")
        except Exception as e:
            print(f"{self.colors.RED} Error updating organizations: {e}{self.colors.NC}")
        
        
        input(f"\n{self.colors.BLUE}Press Enter to return to splash screen...{self.colors.NC}")
        # Return to splash screen
        self.show_boot_splash()
    
    def reset_password(self):
        """Reset web manager password"""
        print(f"\n{self.colors.YELLOW}Resetting Web Manager Password...{self.colors.NC}")
        try:
            now = datetime.now().isoformat()
            data = {
                'username': 'admin',
                'password_hash': '',
                'created_at': now,
                'updated_at': now,
                'needs_reset': True,
            }
            if self.credentials_file.exists():
                try:
                    with open(self.credentials_file, 'r', encoding='utf-8') as f:
                        existing = json.load(f)
                    if isinstance(existing, dict):
                        data.update(existing)
                except Exception:
                    pass
            data['password_hash'] = ''
            data['needs_reset'] = True
            data['updated_at'] = now
            self.credentials_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.credentials_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
            try:
                self.credentials_file.chmod(0o600)
            except Exception:
                pass
            print(f"{self.colors.GREEN}Credentials marked for reset{self.colors.NC}")
            print(f"{self.colors.CYAN}Next web login will prompt for a new admin password.{self.colors.NC}")
        except Exception as e:
            print(f"{self.colors.RED}Error resetting password: {e}{self.colors.NC}")
        
        input(f"\n{self.colors.BLUE}Press Enter to return to splash screen...{self.colors.NC}")
        # Return to splash screen
        self.show_boot_splash()
    def enable_ssh(self):
        """Enable SSH access"""
        print(f"\n{self.colors.YELLOW}Enabling SSH Access...{self.colors.NC}")
        try:
            # Try to run the menu script to enable SSH
            result = subprocess.run([
                'python3', '/home/ubuntu/.cache/pex/user_code/0/d9035d1d7158da90c087665c7c9d7ce7e0506faa/menu.py'
            ], input='8\n7\n0\n0\n', text=True, capture_output=True, timeout=30)
            
            if result.returncode == 0:
                print(f"{self.colors.GREEN}SSH access enabled successfully{self.colors.NC}")
            else:
                print(f"{self.colors.RED}SSH enable failed. You can run this manually from the main menu.{self.colors.NC}")
        except subprocess.TimeoutExpired:
            print(f"{self.colors.YELLOW}SSH enable timed out. You can run this manually from the main menu.{self.colors.NC}")
        except Exception as e:
            print(f"{self.colors.RED}Error enabling SSH: {e}{self.colors.NC}")
            print(f"{self.colors.YELLOW}You can run this manually from the main menu.{self.colors.NC}")
        
        input(f"\n{self.colors.BLUE}Press Enter to return to splash screen...{self.colors.NC}")
        # Return to splash screen
        self.show_boot_splash()
    
def main():
    """Main entry point"""
    try:
        splash = NuNetBootSplash()
        splash.show_boot_splash()
            
    except Exception as e:
        print(f"Error displaying boot splash: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
