"""
Log viewer module for NuNet
"""

import subprocess
from pathlib import Path
from typing import Dict, Literal

LogType = Literal["dms", "deployments"]

class LogViewer:
    def __init__(self):
        self.home_dir = Path.home()
        self.dms_log = Path("/home/nunet/logs/nunet-dms.log")
        self.deployments_log = self.home_dir / "nunet" / "appliance" / "deployment_logs" / "deployments.log"

    def view_log(self, log_type: LogType) -> Dict[str, str]:
        """
        View a specific log file using lnav
        
        Args:
            log_type: Type of log to view (dms or deployments)
            
        Returns:
            Dictionary with view status and message
        """
        try:
            # Check if lnav is installed
            subprocess.run(['which', 'lnav'], check=True, capture_output=True)
            
            log_path = self.dms_log if log_type == "dms" else self.deployments_log
            
            if not log_path.exists():
                return {
                    "status": "error",
                    "message": f"Log file not found: {log_path}"
                }

            # Show usage instructions
            instructions = (
                "Log Viewer Controls:\n"
                "d - filters out debug\n"
                "l - filters out libp2p\n"
                "q - quit viewer\n"
                "\nPress Enter to open the log viewer..."
            )
            print(instructions)
            input()  # Wait for user to press Enter
            
            try:
                subprocess.run(['lnav', str(log_path)], check=True)
                return {
                    "status": "success",
                    "message": "Log viewer closed"
                }
            except subprocess.CalledProcessError as e:
                return {
                    "status": "error",
                    "message": f"Error running log viewer: {str(e)}"
                }

        except subprocess.CalledProcessError:
            return {
                "status": "error",
                "message": "lnav is not installed. Please install it using:\nsudo apt-get install lnav"
            }
        except Exception as e:
            return {
                "status": "error",
                "message": f"Error viewing log: {str(e)}"
            }

    def view_dms_log(self) -> Dict[str, str]:
        """View the DMS log file"""
        return self.view_log("dms")

    def view_deployments_log(self) -> Dict[str, str]:
        """View the deployments log file"""
        return self.view_log("deployments") 