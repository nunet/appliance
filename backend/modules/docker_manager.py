"""
Minimal Docker management helpers used by DDNS flows.
"""

from __future__ import annotations

import json
import subprocess
from typing import Dict, List, Optional


class DockerManager:
    """Lightweight wrapper around docker CLI commands."""

    @staticmethod
    def check_docker_status() -> Dict[str, str]:
        """Return whether the Docker service is active."""
        try:
            subprocess.run(
                ["systemctl", "is-active", "docker"],
                capture_output=True,
                check=True,
            )
            return {"status": "Running", "message": "Docker is running"}
        except subprocess.CalledProcessError:
            return {"status": "Not Running", "message": "Docker is NOT running!"}

    @staticmethod
    def get_running_containers() -> Dict[str, Optional[List[Dict[str, str]]]]:
        """List running containers with basic metadata."""
        try:
            subprocess.run(["docker", "--version"], capture_output=True, check=True)

            result = subprocess.run(
                ["docker", "ps", "--format", "{{json .}}"],
                capture_output=True,
                text=True,
                check=True,
            )

            containers: List[Dict[str, str]] = []
            for line in (result.stdout or "").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue
                containers.append(
                    {
                        "id": payload.get("ID", ""),
                        "name": payload.get("Names", ""),
                        "status": payload.get("Status", ""),
                    }
                )

            return {
                "status": "success",
                "containers": containers if containers else None,
                "message": None if containers else "No containers are currently running.",
            }
        except FileNotFoundError:
            return {"status": "error", "containers": None, "message": "Docker is not installed."}
        except subprocess.CalledProcessError as exc:
            return {
                "status": "error",
                "containers": None,
                "message": f"Error running Docker command: {exc}",
            }
