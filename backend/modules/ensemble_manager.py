"""
Ensemble management module for NuNet
"""

import os
import subprocess
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from .dms_utils import run_dms_command_with_passphrase
from .utils import get_current_branch, Colors, print_header, print_menu_option, pause

class EnsembleManager:
    def __init__(self):
        """Initialize the EnsembleManager"""
        self.home_dir = Path.home()
        self.base_dir = self.home_dir / "ensembles"
        self.log_dir = self.home_dir / "nunet" / "appliance" / "deployment_logs"
        # Default settings for example ensembles
        self.repo = "nunet/solutions/nunet-appliance"
        self.source_dir = "ensembles/examples"

    def _ensure_directories(self):
        """Ensure required directories exist"""
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def get_ensemble_files(self) -> List[Tuple[int, Path]]:
        """Get all ensemble files with their indices"""
        self._ensure_directories()  # Only create when needed
        files = sorted(self.base_dir.rglob("*"))
        files = [f for f in files if f.is_file()]
        return [(i+1, f) for i, f in enumerate(files)]

    def view_running_ensembles(self) -> Dict[str, str]:
        """View currently running ensembles"""
        try:
            result = run_dms_command_with_passphrase(
                ['nunet', '-c', 'dms', 'actor', 'cmd', '/dms/node/deployment/list'],
                capture_output=True,
                text=True,
                check=True
            )
            return {"status": "success", "message": result.stdout}
        except subprocess.CalledProcessError as e:
            return {"status": "error", "message": str(e)}

    def deploy_ensemble(self, file_path: Path, timeout: int = 60) -> Dict[str, str]:
        """Deploy an ensemble with the specified timeout"""
        try:
            self._ensure_directories()  # Only create when needed
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            log_message = f"Submitting deployment on {timestamp} for: {file_path}\n"
            
            with open(self.log_dir / "deployments.log", "a") as log:
                log.write(log_message)
                
                result = run_dms_command_with_passphrase(
                    ['nunet', '-c', 'dms', 'actor', 'cmd', '/dms/node/deployment/new',
                     '-t', f"{timeout}s", '-f', str(file_path)],
                    capture_output=True,
                    text=True,
                    check=True
                )
                
                success_msg = "Ensemble was submitted successfully.\n"
                log.write(success_msg + result.stdout + "\n")
                
                return {
                    "status": "success",
                    "message": success_msg + result.stdout
                }
                
        except subprocess.CalledProcessError as e:
            error_msg = f"Ensemble deployment unsuccessful.\nError: {str(e)}\n"
            with open(self.log_dir / "deployments.log", "a") as log:
                log.write(error_msg)
            return {"status": "error", "message": error_msg}

    def edit_ensemble(self, file_path: Path) -> Dict[str, str]:
        """Open ensemble file in the default editor"""
        try:
            editor = os.environ.get('EDITOR', 'nano')
            subprocess.run([editor, str(file_path)], check=True)
            
            with open(file_path, 'r') as f:
                content = f.read()
                
            return {
                "status": "success",
                "message": f"File updated. New contents:\n{content}"
            }
        except subprocess.CalledProcessError as e:
            return {"status": "error", "message": f"Error editing file: {str(e)}"}
        except Exception as e:
            return {"status": "error", "message": f"Error: {str(e)}"}

    def delete_ensemble(self, file_path: Path) -> Dict[str, str]:
        """Delete an ensemble file"""
        try:
            file_path.unlink()
            return {
                "status": "success",
                "message": f"File {file_path.name} deleted successfully"
            }
        except Exception as e:
            return {"status": "error", "message": f"Error deleting file: {str(e)}"}

    def copy_ensemble(self, source: Path, dest: Path) -> Dict[str, str]:
        """Copy an ensemble file to a new location"""
        try:
            # Ensure destination directory exists
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, dest)
            return {
                "status": "success",
                "message": f"File copied from {source.name} to {dest}"
            }
        except Exception as e:
            return {"status": "error", "message": f"Error copying file: {str(e)}"}

    def download_example_ensembles(
        self,
        repo: str = "nunet/solutions/nunet-appliance",
        branch: str = None,
        source_dir: str = "ensembles/examples",
        target_dir: Optional[Path] = None
    ) -> Dict[str, str]:
        """Download example ensembles from a Git repository"""
        self._ensure_directories()
        target_dir = target_dir or self.base_dir
        
        try:
            # Get the current branch if none specified
            if branch is None:
                branch = get_current_branch()
            
            print(f"\nDebug info:")
            print(f"Using branch: {branch}")
            print(f"Repository: {repo}")
            print(f"Source directory: {source_dir}")
            print(f"Target directory: {target_dir}")

            # Create a temporary directory for cloning
            temp_dir = Path("/tmp/nunet-examples")
            if temp_dir.exists():
                shutil.rmtree(temp_dir)
            
            print(f"\nCloning repository...")
            clone_result = subprocess.run(
                ['git', 'clone', '-b', branch, f'https://gitlab.com/{repo}.git', str(temp_dir)],
                capture_output=True,
                text=True
            )
            
            if clone_result.returncode != 0:
                print(f"\nGit clone error:")
                print(f"Return code: {clone_result.returncode}")
                print(f"Stdout: {clone_result.stdout}")
                print(f"Stderr: {clone_result.stderr}")
                return {"status": "error", "message": f"Git clone failed: {clone_result.stderr}"}
            
            # Copy example ensembles
            source_path = temp_dir / source_dir
            print(f"\nLooking for ensembles in: {source_path}")
            
            if not source_path.exists():
                return {
                    "status": "error",
                    "message": f"Source directory {source_dir} not found in repository"
                }
            
            # List files found
            print("\nFiles found in source directory:")
            for item in source_path.glob("*"):
                print(f"Found: {item}")
            
            # Copy all files from source to target
            files_copied = 0
            for item in source_path.glob("*"):
                if item.is_file():
                    shutil.copy2(item, target_dir)
                    files_copied += 1
                    print(f"Copied: {item.name} to {target_dir}")
                else:
                    shutil.copytree(item, target_dir / item.name, dirs_exist_ok=True)
                    files_copied += 1
                    print(f"Copied directory: {item.name}")
            
            # Cleanup
            shutil.rmtree(temp_dir)
            
            if files_copied == 0:
                return {
                    "status": "warning",
                    "message": f"No files found to copy in {source_dir}"
                }
            
            return {
                "status": "success",
                "message": f"Successfully copied {files_copied} items to {target_dir}"
            }
            
        except subprocess.CalledProcessError as e:
            return {"status": "error", "message": f"Git operation failed: {str(e)}"}
        except Exception as e:
            return {"status": "error", "message": f"Error downloading examples: {str(e)}"}

    def download_example_ensembles_menu(self) -> Dict[str, str]:
        """Interactive menu for downloading example ensemble templates"""
        print_header("Download Example Ensemble Templates")
        print("\nThis will download example ensemble templates from the NuNet repository.")
        print("The templates will be saved in your ensembles directory.")
        print()
        
        # Get current branch for context
        current_branch = get_current_branch()
        print(f"Current branch: {Colors.GREEN}{current_branch}{Colors.NC}")
        print()

        if input("Would you like to use these default settings? [Y/n]: ").lower() != 'n':
            return self.download_example_ensembles()
        else:
            repo = input(f"Enter repository [{self.repo}]: ") or self.repo
            branch = input(f"Enter branch [{current_branch}]: ") or current_branch
            source_dir = input(f"Enter source directory [{self.source_dir}]: ") or self.source_dir
            target_dir = input(f"Enter target directory [{str(self.base_dir)}]: ") or str(self.base_dir)
            
            return self.download_example_ensembles(
                repo=repo,
                branch=branch,
                source_dir=source_dir,
                target_dir=Path(target_dir)
            )

    def deploy_ensemble_menu(self) -> None:
        """Menu for deploying ensembles"""
        print_header("Deploy Ensemble")
        
        # Get available ensembles
        ensembles = self.get_ensemble_files()
        if not ensembles:
            print("No ensembles found.")
            pause()
            return

        print("Available Ensembles:")
        for idx, file_path in ensembles:
            print(f"{idx:3d}) {file_path.relative_to(self.base_dir)}")
        print()

        try:
            file_number = int(input("Select an ensemble to deploy by number: "))
            if file_number < 1 or file_number > len(ensembles):
                print(f"{Colors.RED}Invalid selection.{Colors.NC}")
                pause()
                return

            selected_file = ensembles[file_number - 1][1]

            # Display file contents
            print("\n-------------------------------------")
            print(f"Contents of {selected_file.name}:")
            print("-------------------------------------")
            with open(selected_file, 'r') as f:
                print(f.read())
            print("-------------------------------------\n")

            # Get user action
            print("Options:")
            print("  e) Edit the ensemble")
            print("  r) Run the ensemble")
            print("  c) Cancel deployment")
            action = input("Choose an option: ").lower()

            if action == 'e':
                result = self.edit_ensemble(selected_file)
                print(result['message'])
            elif action == 'r':
                timeout = input("Enter deployment timeout in seconds (default 60): ") or "60"
                try:
                    timeout = int(timeout)
                except ValueError:
                    print(f"{Colors.RED}Invalid timeout value. Using default 60 seconds.{Colors.NC}")
                    timeout = 60

                confirm = input("Would you like to run this ensemble now? (r to run, any other key to cancel): ").lower()
                if confirm == 'r':
                    result = self.deploy_ensemble(selected_file, timeout)
                    print(result['message'])
                else:
                    print("Deployment cancelled.")
            else:
                print("Deployment cancelled.")

        except ValueError:
            print(f"{Colors.RED}Invalid input.{Colors.NC}")
        
        pause()

    def manage_ensemble_templates_menu(self) -> None:
        """Menu for managing ensemble templates"""
        while True:
            print_header("Manage Ensemble Templates")
            
            # Get available ensembles
            ensembles = self.get_ensemble_files()
            if ensembles:
                print("Available Ensembles:")
                for idx, file_path in ensembles:
                    print(f"{idx:3d}) {file_path.relative_to(self.base_dir)}")
            else:
                print("No ensemble files found.")
            print("\nOptions:")
            print_menu_option("1", "Open an ensemble file")
            print_menu_option("2", "Delete an ensemble file")
            print_menu_option("3", "Copy an ensemble file")
            print_menu_option("0", "Return to Previous Menu")
            print()

            choice = input("Select an option: ")

            if choice in ["1", "2", "3"]:
                if not ensembles:
                    print(f"{Colors.RED}No files available.{Colors.NC}")
                    pause()
                    continue

                try:
                    file_number = int(input("Enter the number of the ensemble: "))
                    if file_number < 1 or file_number > len(ensembles):
                        print(f"{Colors.RED}Invalid selection.{Colors.NC}")
                        pause()
                        continue

                    selected_file = ensembles[file_number - 1][1]

                    if choice == "1":
                        result = self.edit_ensemble(selected_file)
                    elif choice == "2":
                        confirm = input(f"Are you sure you want to delete '{selected_file.name}'? [y/N]: ").lower()
                        if confirm == 'y':
                            result = self.delete_ensemble(selected_file)
                        else:
                            result = {"status": "info", "message": "Deletion cancelled."}
                    else:  # choice == "3"
                        dest_path = input("Enter the destination path (relative to ~/ensembles): ")
                        dest_file = self.base_dir / dest_path
                        result = self.copy_ensemble(selected_file, dest_file)

                    print(result['message'])
                    pause()

                except ValueError:
                    print(f"{Colors.RED}Invalid input.{Colors.NC}")
                    pause()

            elif choice == "0":
                break
            else:
                print(f"{Colors.RED}Invalid option!{Colors.NC}")
                pause() 