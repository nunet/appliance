"""
NuNet Appliance management module
"""
import sys
import subprocess
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
import tempfile
import hashlib
from .utils import get_current_branch, set_current_branch, get_appliance_dir

class ApplianceManager:
    def __init__(self):
        self.home_dir = get_appliance_dir()
        self.version_file = self.home_dir / "version.txt"
        self.backup_dir = self.home_dir / "backups"
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        self.known_orgs_file = self.home_dir / "known_orgs" / "known_organizations.json"
        self.remote_orgs_url = "https://gitlab.com/nunet/solutions/nunet-appliance/-/raw/auki-node-pre-reqs-and-web/config/known_orgs/known_organizations.json?ref_type=heads"


    def get_current_version(self) -> str:
        """Get current version from version.txt in menu root"""
        try:
            version_file = Path(__file__).parent.parent / "version.txt"
            return version_file.read_text().strip()
        except FileNotFoundError:
            return "unknown"

    def check_for_updates(self, branch: str = None) -> Dict[str, str]:
        """Check if updates are available"""
        try:
            current_version = self.get_current_version()
            current_branch = get_current_branch()
            
            if branch is None:
                branch = current_branch

            # Get the remote version directly from GitLab raw file
            fetch_result = subprocess.run(
                ["curl", "-s", f"https://gitlab.com/nunet/solutions/nunet-appliance/-/raw/{branch}/src/menu/version.txt?ref_type=heads"],
                capture_output=True,
                text=True
            )
            
            if fetch_result.returncode != 0:
                return {
                    "status": "error",
                    "message": f"Failed to fetch remote version: {fetch_result.stderr}"
                }

            remote_version = fetch_result.stdout.strip()
            if not remote_version:
                return {
                    "status": "error",
                    "message": "Failed to get remote version (empty response)"
                }

            return {
                "status": "success",
                "current_version": current_version,
                "remote_version": remote_version,
                "current_branch": current_branch,
                "update_available": current_version != remote_version
            }

        except subprocess.CalledProcessError as e:
            return {
                "status": "error",
                "message": f"Error checking for updates: {str(e)}"
            }
        except Exception as e:
            return {
                "status": "error",
                "message": f"Error checking for updates: {str(e)}"
            }

    def update_appliance(self, branch: str = None) -> Dict[str, str]:
        """Update the appliance"""
        try:
            if branch is None:
                branch = get_current_branch()
            else:
                # Update the branch file if a new branch is specified
                set_current_branch(branch)

            # Store the current branch before update
            current_branch = get_current_branch()

            # Run the update
            process = subprocess.Popen(
                [str(self.home_dir / "get-menu.sh"), branch],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True
            )

            # Collect output for the final result
            output_lines = []
            
            # Read and display output in real-time
            while True:
                line = process.stdout.readline()
                if not line and process.poll() is not None:
                    break
                if line:
                    print(line.rstrip())  # Print in real-time
                    output_lines.append(line.rstrip())

            # Wait for process to complete and get return code
            return_code = process.wait()

            # Restore the branch information after update
            set_current_branch(current_branch)

            if return_code == 0:
                return {
                    "status": "success",
                    "message": "Appliance updated successfully. Please restart the menu to use the new version.",
                    "details": "\n".join(output_lines)
                }
            else:
                return {
                    "status": "error",
                    "message": f"Error updating appliance (exit code {return_code})",
                    "details": "\n".join(output_lines)
                }

        except subprocess.CalledProcessError as e:
            return {
                "status": "error",
                "message": f"Error updating appliance: {str(e)}",
                "details": e.output if hasattr(e, 'output') else None
            }
        except Exception as e:
            return {
                "status": "error",
                "message": f"Error updating appliance: {str(e)}"
            }

    def redownload_menu(self, branch: str = None) -> Dict[str, str]:
        """Force re-download of the menu from GitLab"""

        
        try:
            if branch is None:
                branch = get_current_branch()
            else:
                # Update the branch file if a new branch is specified
                set_current_branch(branch)
            current_branch = branch
            # Store the current branch before re-download
            branch = input(f"Enter branch to download [{current_branch}]: ") or current_branch
            set_current_branch(branch)
            
            # Run get-menu.sh with --force flag and show output in real-time
            process = subprocess.Popen(
                [str(self.home_dir / "get-menu.sh"), branch, "--force"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True
            )

            # Collect output for the final result
            output_lines = []
            
            # Read and display output in real-time
            while True:
                line = process.stdout.readline()
                if not line and process.poll() is not None:
                    break
                if line:
                    print(line.rstrip())  # Print in real-time
                    output_lines.append(line.rstrip())

            # Wait for process to complete and get return code
            return_code = process.wait()

            # Restore the branch information after re-download
            set_current_branch(current_branch)

            if return_code == 0:
                return {
                    "status": "success",
                    "message": "Menu re-downloaded successfully. Please restart the menu to use the fresh version.",
                    "details": "\n".join(output_lines)
                }
            else:
                return {
                    "status": "error",
                    "message": f"Error re-downloading menu (exit code {return_code})",
                    "details": "\n".join(output_lines)
                }

        except subprocess.CalledProcessError as e:
            return {
                "status": "error",
                "message": f"Error re-downloading menu: {str(e)}",
                "details": e.output if hasattr(e, 'output') else None
            }
        except Exception as e:
            return {
                "status": "error",
                "message": f"Error re-downloading menu: {str(e)}"
            }

    def manage_plugins(self) -> Dict[str, str]:
        """Manage plugins using the plugin manager script"""
        try:
            result = subprocess.run(
                [str(self.home_dir / "plugin-manager.sh")],
                check=True,
                capture_output=True,
                text=True
            )
            return {
                "status": "success",
                "message": "Plugin manager executed successfully.",
                "details": result.stdout
            }
        except subprocess.CalledProcessError as e:
            return {
                "status": "error",
                "message": f"Error managing plugins: {str(e)}"
            }

    def backup_appliance(self) -> Dict[str, str]:
        """Create a backup of the appliance configuration"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = self.backup_dir / f"backup_{timestamp}.tar.gz"
            
            # Create backup of important directories and files
            result = subprocess.run(
                ["tar", "-czf", str(backup_path),
                 "-C", str(self.home_dir),
                 "config",
                 "version",
                 "branch",
                 "plugins"],
                check=True,
                capture_output=True,
                text=True
            )
            
            return {
                "status": "success",
                "message": f"Backup created successfully at {backup_path}",
                "backup_path": str(backup_path)
            }
        except subprocess.CalledProcessError as e:
            return {
                "status": "error",
                "message": f"Error creating backup: {str(e)}"
            }

    def list_backups(self) -> Dict[str, List[str]]:
        """List available backups"""
        try:
            backups = sorted(
                [str(f.name) for f in self.backup_dir.glob("backup_*.tar.gz")],
                reverse=True
            )
            return {
                "status": "success",
                "backups": backups
            }
        except Exception as e:
            return {
                "status": "error",
                "message": f"Error listing backups: {str(e)}",
                "backups": []
            }

    def restore_appliance(self, backup_name: str) -> Dict[str, str]:
        """Restore appliance from a backup"""
        try:
            backup_path = self.backup_dir / backup_name
            if not backup_path.exists():
                return {
                    "status": "error",
                    "message": f"Backup file {backup_name} not found"
                }

            # Create a temporary directory for extraction
            result = subprocess.run(
                ["tar", "-xzf", str(backup_path),
                 "-C", str(self.home_dir)],
                check=True,
                capture_output=True,
                text=True
            )

            return {
                "status": "success",
                "message": "Appliance configuration restored successfully. Please restart the menu to apply changes."
            }
        except subprocess.CalledProcessError as e:
            return {
                "status": "error",
                "message": f"Error restoring backup: {str(e)}"
            }

    def get_appliance_info(self) -> Dict[str, str]:
        """Get information about the NuNet appliance"""
        try:
            script_path = self.home_dir / "get-appliance-info.sh"
            if not script_path.exists():
                return {
                    "status": "error",
                    "message": f"Info script not found at {script_path}"
                }
            
            result = subprocess.run(
                ['sudo', '-u', 'ubuntu', str(script_path)],
                check=True,
                capture_output=True,
                text=True
            )
            return {"status": "success", "message": result.stdout}
        except subprocess.CalledProcessError as e:
            return {"status": "error", "message": f"Error getting appliance info: {str(e)}"}

    def change_branch_interactive(self):
        """Interactively change the active branch"""
        try:
            from modules.utils import get_current_branch, set_current_branch  # Make sure we import set_current_branch
            
            current_branch = get_current_branch()
            print(f"Current branch: {current_branch}")
            new_branch = input("Enter new branch name (or press Enter to cancel): ").strip()
            
            if not new_branch:
                print("Branch change cancelled.")
                return
            
            # Use set_current_branch instead of directly writing to file
            set_current_branch(new_branch)
            print(f"Successfully changed branch to: {new_branch}")
            
        except Exception as e:
            print(f"Error changing branch: {str(e)}")

    def check_and_update_appliance_interactive(self):
        """Check for and install appliance updates"""
        try:
            current_branch = get_current_branch()
            print(f"Checking for updates on branch: {current_branch}")
            
            result = self.check_for_updates()
            if result.get('status') != 'success':
                print(result.get('message', 'Error checking for updates.'))
                return

            # Validate remote version - check if it's HTML (error page) or invalid
            remote_version = result.get('remote_version', 'unknown')
            if remote_version.startswith('<!DOCTYPE') or remote_version.startswith('<html'):
                print(f"Error: Could not fetch remote version for branch '{current_branch}'")
                print("This might be because the branch doesn't exist or there was a connection error.")
                return
            
            print(f"Current version: {result.get('current_version', 'unknown')}")
            print(f"Remote version: {remote_version}")
            
            if result.get('update_available', False):
                print("\nUpdate is available!")
                confirm = input("Do you want to install the update? (y/N): ").strip().lower()
                if confirm == 'y':
                    update_result = self.update_appliance()
                    print(update_result.get('message', 'No message returned.'))
                else:
                    print("Update cancelled.")
            else:
                print("\nNo updates available.")
            
        except Exception as e:
            print(f"Error during update process: {str(e)}")

    def redownload_menu_interactive(self):
        """Force re-download of the menu from GitLab with confirmation"""
        try:
            current_branch = get_current_branch()
            print(f"Current branch: {current_branch}")
            print("\nWARNING: This will re-download the entire menu from GitLab.")
            confirm = input("Are you sure you want to proceed? (y/N): ").strip().lower()
            
            if confirm != 'y':
                print("Re-download cancelled.")
                return
            
            result = self.redownload_menu(current_branch)
            print(result.get('message', 'No message returned.'))
            if result.get('status') == 'success':
                print("Please restart the menu to use the fresh version.")
            
        except Exception as e:
            print(f"Error re-downloading menu: {str(e)}") 

    def enable_ssh_access(self):
        """Run the SSH configuration script interactively."""
        script_path = Path(__file__).parent.parent / "scripts" / "configure-ssh-access-wrapper.py"
        print(f"Running SSH configuration script: {script_path}")
        try:
            subprocess.run([sys.executable, str(script_path)])
        except Exception as e:
            print(f"Error running SSH configuration script: {e}")
        # Optionally, you can return a status/message dict for consistency
        return {"status": "success", "message": "SSH configuration script executed."}

    def run_os_updates_interactive(self):
        print("\033[93mChecking for and applying OS updates...\033[0m\n")
        try:
            # Update package lists
            subprocess.run(['sudo', 'apt', 'update'], check=True)
            # Upgrade all packages (non-interactive)
            subprocess.run(['sudo', 'apt', 'upgrade', '-y'], check=True)
            # Optionally, for full upgrade (kernel, etc.):
            # subprocess.run(['sudo', 'apt', 'full-upgrade', '-y'], check=True)
            print("\033[92mOS update completed successfully!\033[0m")
        except subprocess.CalledProcessError as e:
            print(f"\033[91mError during update: {e}\033[0m")


    def get_unattended_upgrades_status(self):
        """
        Returns a dict with:
            - enabled: True/False/None
            - last_run: datetime string or 'Never'
            - last_log: summary of last log line or ''
        """
        status = {
            "enabled": None,
            "last_run": "Unknown",
            "last_log": ""
        }
        # Check if enabled
        try:
            result = subprocess.run(
                ['systemctl', 'is-enabled', 'unattended-upgrades'],
                capture_output=True, text=True, check=False
            )
            status["enabled"] = (result.stdout.strip() == "enabled")
        except Exception:
            status["enabled"] = None

        # Find last run time from log
        try:
            log_path = "/var/log/unattended-upgrades/unattended-upgrades.log"
            with open(log_path, "r") as f:
                lines = f.readlines()
            # Find last line with a date
            for line in reversed(lines):
                if line.strip() and line[0].isdigit():
                    # Example: 2024-06-09 06:25:01,123 INFO ...
                    status["last_run"] = line[:19]
                    status["last_log"] = line.strip()
                    break
            else:
                status["last_run"] = "Never"
        except Exception:
            status["last_run"] = "Never"
            status["last_log"] = ""
        return status

    def enable_unattended_upgrades(self):
        """Enable automatic security updates (unattended-upgrades)."""
        try:
            subprocess.run(['sudo', 'systemctl', 'enable', '--now', 'unattended-upgrades'], check=True)
            print("\033[92mUnattended-upgrades enabled and started.\033[0m")
        except subprocess.CalledProcessError as e:
            print(f"\033[91mFailed to enable unattended-upgrades: {e}\033[0m")


    def disable_unattended_upgrades(self):
        """Disable automatic security updates (unattended-upgrades)."""
        try:
            subprocess.run(['sudo', 'systemctl', 'disable', '--now', 'unattended-upgrades'], check=True)
            print("\033[93mUnattended-upgrades disabled and stopped.\033[0m")
        except subprocess.CalledProcessError as e:
            print(f"\033[91mFailed to disable unattended-upgrades: {e}\033[0m")


    def check_and_update_known_organizations(self) -> Dict[str, str]:
        """Check for updates to known_organizations.json and optionally update"""
        try:
            # Ensure the directory exists
            self.known_orgs_file.parent.mkdir(parents=True, exist_ok=True)
            
            # Check if local file exists
            local_data = {}
            if self.known_orgs_file.exists():
                # Read local file
                try:
                    with open(self.known_orgs_file, 'r') as f:
                        local_data = json.load(f)
                except json.JSONDecodeError as e:
                    return {
                        "status": "error",
                        "message": f"Local known_organizations.json is invalid JSON: {str(e)}"
                    }
            else:
                # Local file doesn't exist - will be created with remote content
                local_data = {}

            # Download remote file
            try:
                result = subprocess.run(
                    ["curl", "-s", self.remote_orgs_url],
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                
                if result.returncode != 0:
                    return {
                        "status": "error",
                        "message": f"Failed to fetch remote file: {result.stderr}"
                    }

                remote_content = result.stdout.strip()
                if not remote_content:
                    return {
                        "status": "error",
                        "message": "Remote file is empty or not accessible"
                    }

                # Check if response is HTML (error page)
                if remote_content.startswith('<!DOCTYPE') or remote_content.startswith('<html'):
                    return {
                        "status": "error",
                        "message": "Remote URL returned HTML instead of JSON (possible error page)"
                    }

                # Parse remote JSON
                try:
                    remote_data = json.loads(remote_content)
                except json.JSONDecodeError as e:
                    return {
                        "status": "error",
                        "message": f"Remote file contains invalid JSON: {str(e)}"
                    }

            except subprocess.TimeoutExpired:
                return {
                    "status": "error",
                    "message": "Timeout while fetching remote file"
                }

            # Compare files
            local_json = json.dumps(local_data, sort_keys=True, indent=2)
            remote_json = json.dumps(remote_data, sort_keys=True, indent=2)
            
            local_hash = hashlib.md5(local_json.encode()).hexdigest()
            remote_hash = hashlib.md5(remote_json.encode()).hexdigest()

            # Check if local file exists
            local_file_exists = self.known_orgs_file.exists()

            if local_hash == remote_hash and local_file_exists:
                return {
                    "status": "success",
                    "message": "Local known_organizations.json is up to date",
                    "local_hash": local_hash,
                    "remote_hash": remote_hash,
                    "update_available": False
                }

            # Files are different or local file doesn't exist - show differences
            differences = []
            if not local_file_exists:
                # Local file doesn't exist - all remote organizations are new
                for org_did, org_data in remote_data.items():
                    differences.append(f"NEW: {org_did} - {org_data.get('name', 'Unknown')}")
            else:
                # Compare existing files
                for org_did in set(local_data.keys()) | set(remote_data.keys()):
                    if org_did not in local_data:
                        differences.append(f"NEW: {org_did} - {remote_data[org_did].get('name', 'Unknown')}")
                    elif org_did not in remote_data:
                        differences.append(f"REMOVED: {org_did} - {local_data[org_did].get('name', 'Unknown')}")
                    elif local_data[org_did] != remote_data[org_did]:
                        differences.append(f"UPDATED: {org_did} - {remote_data[org_did].get('name', 'Unknown')}")

            return {
                "status": "success",
                "message": f"Update available! Found {len(differences)} changes",
                "local_hash": local_hash,
                "remote_hash": remote_hash,
                "update_available": True,
                "differences": differences,
                "remote_data": remote_data
            }

        except Exception as e:
            return {
                "status": "error",
                "message": f"Error checking known organizations: {str(e)}"
            }

    def update_known_organizations(self) -> Dict[str, str]:
        """Update the local known_organizations.json file with remote version"""
        try:
            # First check for updates
            check_result = self.check_and_update_known_organizations()
            
            if check_result.get('status') != 'success':
                return check_result

            if not check_result.get('update_available', False):
                return {
                    "status": "success",
                    "message": "No update needed - file is already up to date"
                }

            # Create backup only if local file exists
            backup_path = None
            if self.known_orgs_file.exists():
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                backup_path = self.known_orgs_file.parent / f"known_organizations_backup_{timestamp}.json"
                
                try:
                    with open(self.known_orgs_file, 'r') as src, open(backup_path, 'w') as dst:
                        dst.write(src.read())
                except Exception as e:
                    return {
                        "status": "error",
                        "message": f"Failed to create backup: {str(e)}"
                    }

            # Update the file
            try:
                remote_data = check_result.get('remote_data')
                with open(self.known_orgs_file, 'w') as f:
                    json.dump(remote_data, f, indent=2)
            except Exception as e:
                return {
                    "status": "error",
                    "message": f"Failed to update file: {str(e)}"
                }

            # Prepare success message
            if backup_path:
                message = f"Successfully updated known_organizations.json. Backup created at {backup_path.name}"
            else:
                message = "Successfully created known_organizations.json from remote source"

            return {
                "status": "success",
                "message": message,
                "backup_path": str(backup_path) if backup_path else None,
                "differences": check_result.get('differences', [])
            }

        except Exception as e:
            return {
                "status": "error",
                "message": f"Error updating known organizations: {str(e)}"
            }

    def check_and_update_known_organizations_interactive(self):
        """Interactive version of check and update known organizations"""
        try:
            print("\033[93mChecking for updates to known organizations...\033[0m")
            
            result = self.check_and_update_known_organizations()
            
            if result.get('status') != 'success':
                print(f"\033[91mError: {result.get('message')}\033[0m")
                return

            if not result.get('update_available', False):
                print(f"\033[92m{result.get('message')}\033[0m")
                return

            # Show differences
            print(f"\033[93m{result.get('message')}\033[0m")
            print("\nChanges detected:")
            for diff in result.get('differences', []):
                print(f"  • {diff}")

            # Ask for confirmation
            confirm = input("\nDo you want to update the local file? (y/N): ").strip().lower()
            if confirm != 'y':
                print("Update cancelled.")
                return

            # Perform update
            update_result = self.update_known_organizations()
            
            if update_result.get('status') == 'success':
                print(f"\033[92m{update_result.get('message')}\033[0m")
                if update_result.get('differences'):
                    print("\nApplied changes:")
                    for diff in update_result.get('differences', []):
                        print(f"  • {diff}")
            else:
                print(f"\033[91mError: {update_result.get('message')}\033[0m")

        except Exception as e:
            print(f"\033[91mError during update process: {str(e)}\033[0m")
