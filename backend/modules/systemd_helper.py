#!/usr/bin/env python3
"""
Systemd service management utility module.
Provides a consistent interface for managing systemd services across the application.
"""

import subprocess
import logging
from typing import Optional, List, Dict, Any
from pathlib import Path

logger = logging.getLogger(__name__)


class SystemdHelper:
    """Utility class for managing systemd services."""
    
    def __init__(self):
        self.systemctl = "/usr/bin/systemctl"
    
    def _run_command(self, command: List[str], capture_output: bool = True) -> subprocess.CompletedProcess:
        """Run a systemctl command and return the result."""
        try:
            result = subprocess.run(
                [self.systemctl] + command,
                capture_output=capture_output,
                text=True,
                timeout=30
            )
            return result
        except subprocess.TimeoutExpired:
            logger.error(f"Command timed out: {' '.join(command)}")
            raise
        except Exception as e:
            logger.error(f"Error running command {' '.join(command)}: {e}")
            raise
    
    def is_active(self, service_name: str) -> bool:
        """Check if a service is currently active."""
        try:
            result = self._run_command(["is-active", service_name])
            return result.returncode == 0
        except Exception as e:
            logger.error(f"Error checking if {service_name} is active: {e}")
            return False
    
    def is_enabled(self, service_name: str) -> bool:
        """Check if a service is enabled to start on boot."""
        try:
            result = self._run_command(["is-enabled", service_name])
            return result.returncode == 0
        except Exception as e:
            logger.error(f"Error checking if {service_name} is enabled: {e}")
            return False
    
    def start(self, service_name: str) -> bool:
        """Start a service."""
        try:
            result = self._run_command(["start", service_name])
            if result.returncode == 0:
                logger.info(f"Successfully started {service_name}")
                return True
            else:
                logger.error(f"Failed to start {service_name}: {result.stderr}")
                return False
        except Exception as e:
            logger.error(f"Error starting {service_name}: {e}")
            return False
    
    def stop(self, service_name: str) -> bool:
        """Stop a service."""
        try:
            result = self._run_command(["stop", service_name])
            if result.returncode == 0:
                logger.info(f"Successfully stopped {service_name}")
                return True
            else:
                logger.error(f"Failed to stop {service_name}: {result.stderr}")
                return False
        except Exception as e:
            logger.error(f"Error stopping {service_name}: {e}")
            return False
    
    def restart(self, service_name: str) -> bool:
        """Restart a service."""
        try:
            result = self._run_command(["restart", service_name])
            if result.returncode == 0:
                logger.info(f"Successfully restarted {service_name}")
                return True
            else:
                logger.error(f"Failed to restart {service_name}: {result.stderr}")
                return False
        except Exception as e:
            logger.error(f"Error restarting {service_name}: {e}")
            return False
    
    def enable(self, service_name: str) -> bool:
        """Enable a service to start on boot."""
        try:
            result = self._run_command(["enable", service_name])
            if result.returncode == 0:
                logger.info(f"Successfully enabled {service_name}")
                return True
            else:
                logger.error(f"Failed to enable {service_name}: {result.stderr}")
                return False
        except Exception as e:
            logger.error(f"Error enabling {service_name}: {e}")
            return False
    
    def disable(self, service_name: str) -> bool:
        """Disable a service from starting on boot."""
        try:
            result = self._run_command(["disable", service_name])
            if result.returncode == 0:
                logger.info(f"Successfully disabled {service_name}")
                return True
            else:
                logger.error(f"Failed to disable {service_name}: {result.stderr}")
                return False
        except Exception as e:
            logger.error(f"Error disabling {service_name}: {e}")
            return False
    
    def get_status(self, service_name: str) -> Dict[str, Any]:
        """Get detailed status information for a service."""
        try:
            result = self._run_command(["show", "--property=ActiveState,LoadState,UnitFileState", service_name])
            if result.returncode == 0:
                status = {}
                for line in result.stdout.strip().split('\n'):
                    if '=' in line:
                        key, value = line.split('=', 1)
                        status[key] = value
                return status
            else:
                logger.error(f"Failed to get status for {service_name}: {result.stderr}")
                return {}
        except Exception as e:
            logger.error(f"Error getting status for {service_name}: {e}")
            return {}
    
    def get_logs(self, service_name: str, lines: int = 50) -> List[str]:
        """Get recent logs for a service."""
        try:
            result = self._run_command(["journalctl", "-u", service_name, "-n", str(lines), "--no-pager"])
            if result.returncode == 0:
                return result.stdout.strip().split('\n')
            else:
                logger.error(f"Failed to get logs for {service_name}: {result.stderr}")
                return []
        except Exception as e:
            logger.error(f"Error getting logs for {service_name}: {e}")
            return []
    
    def reload_daemon(self) -> bool:
        """Reload systemd daemon to pick up new service files."""
        try:
            result = self._run_command(["daemon-reload"])
            if result.returncode == 0:
                logger.info("Successfully reloaded systemd daemon")
                return True
            else:
                logger.error(f"Failed to reload systemd daemon: {result.stderr}")
                return False
        except Exception as e:
            logger.error(f"Error reloading systemd daemon: {e}")
            return False
    
    def service_exists(self, service_name: str) -> bool:
        """Check if a service file exists."""
        service_path = Path(f"/etc/systemd/system/{service_name}")
        return service_path.exists()


# Global instance for easy access
systemd_helper = SystemdHelper() 