import subprocess
from typing import Dict, List

_SERVICES: List[str] = [
    "nunet-appliance-web.service",
    "nunet-appliance-updater.service",
    "nunet-dms-updater.service",
    "alloy.service",
    "nunet-caddy-proxy-monitor.service",
    "avahi-daemon.service",
]


class ApplianceManager:
    """Manager for appliance-level operations."""

    def get_uptime(self) -> str:
        """
        Reads system uptime from /proc/uptime and returns it as a human-readable string.
        """
        try:
            with open('/proc/uptime', 'r') as f:
                uptime_seconds = float(f.readline().split()[0])

            days = int(uptime_seconds // (24 * 3600))
            uptime_seconds %= (24 * 3600)
            hours = int(uptime_seconds // 3600)
            uptime_seconds %= 3600
            minutes = int(uptime_seconds // 60)

            parts = []
            if days > 0:
                parts.append(f"{days} day{'s' if days != 1 else ''}")
            if hours > 0:
                parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
            if minutes > 0:
                parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")

            if not parts:
                return "Less than a minute"

            return ", ".join(parts)
        except (FileNotFoundError, IndexError, ValueError) as e:
            return f"Could not determine uptime: {e}"

    def get_systemd_logs(self, lines: int = 50) -> Dict[str, str]:
        """
        Fetches the latest log entries from systemd-journald for a predefined list of services.

        :param lines: The number of log lines to retrieve for each service.
        :return: A dictionary where keys are service names and values are their log outputs.
        """
        logs = {}
        for service in _SERVICES:
            try:
                cmd = ["journalctl", "-u", service, "-n", str(lines), "--no-pager"]
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    check=False,
                )

                if result.returncode != 0:
                    logs[service] = f"Error fetching logs: {result.stderr.strip()}"
                elif not result.stdout:
                    logs[service] = (
                        f"No log entries found for '{service}'. Verify the service name is correct and that the user "
                        "running this application has permissions to read its logs (e.g., is in the 'systemd-journal' group)."
                    )
                else:
                    logs[service] = result.stdout
            except FileNotFoundError:
                logs[service] = "Error: 'journalctl' command not found. Is systemd running?"
            except Exception as e:
                logs[service] = f"An unexpected error occurred: {e}"
        return logs
