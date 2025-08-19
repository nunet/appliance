"""
Docker management module
"""

import subprocess
from typing import Dict, List, Optional

class DockerManager:
    @staticmethod
    def check_docker_status() -> Dict[str, str]:
        """Check if Docker service is running"""
        try:
            subprocess.run(
                ['systemctl', 'is-active', 'docker'],
                capture_output=True,
                check=True
            )
            return {
                "status": "Running",
                "message": "Docker is running"
            }
        except subprocess.CalledProcessError:
            return {
                "status": "Not Running",
                "message": "Docker is NOT running!"
            }

    @staticmethod
    def get_running_containers() -> Dict[str, Optional[List[Dict[str, str]]]]:
        """Get list of running Docker containers"""
        try:
            # Check if docker is installed
            subprocess.run(['docker', '--version'], capture_output=True, check=True)
            
            # Get running containers
            result = subprocess.run(
                ['docker', 'ps', '--format', '{"id":"{{.ID}}", "name":"{{.Names}}", "status":"{{.Status}}"}'],
                capture_output=True,
                text=True,
                check=True
            )
            
            # Parse the output into a list of dictionaries
            containers = []
            for line in result.stdout.splitlines():
                if line.strip():  # Skip empty lines
                    try:
                        containers.append(eval(line))  # Safe since we control the format
                    except:
                        continue
                        
            return {
                "status": "success",
                "containers": containers if containers else None,
                "message": "No containers are currently running" if not containers else None
            }
            
        except FileNotFoundError:
            return {
                "status": "error",
                "containers": None,
                "message": "Docker is not installed"
            }
        except subprocess.CalledProcessError as e:
            return {
                "status": "error",
                "containers": None,
                "message": f"Error running Docker command: {str(e)}"
            } 

    def view_docker_containers(self):
        """View running Docker containers"""
        from .utils import Colors, print_header, pause  # Import required utilities
        
        print_header("Docker Containers")
        result = self.get_running_containers()  # Changed from self.docker_manager to self
        
        if result['status'] == 'error':
            print(f"{Colors.RED}{result['message']}{Colors.NC}")
        elif not result['containers']:
            print("✅ No containers are currently running.")
        else:
            print("🟢 Active Containers:")
            for container in result['containers']:
                print(f"ID: {container['id']}")
                print(f"Name: {container['name']}")
                print(f"Status: {container['status']}")
                print("-" * 30)
        
        pause()