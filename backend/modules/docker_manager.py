"""Docker management helpers used by the NuNet appliance backend."""

from __future__ import annotations

import json
import shutil
import subprocess
from typing import Any, Dict, List, Optional

from .logging_config import get_logger

logger = get_logger(__name__)


class DockerService:
    """Thin wrapper around common Docker CLI interactions."""

    def __init__(self) -> None:
        self._docker_path = shutil.which("docker")
        if not self._docker_path:
            logger.debug("Docker binary not found on PATH")

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _run(command: List[str]) -> subprocess.CompletedProcess[str]:
        """Execute *command* capturing stdout/stderr without raising."""
        logger.debug("Executing command", extra={"command": command})
        return subprocess.run(command, capture_output=True, text=True, check=False)

    def _ensure_docker_available(self) -> bool:
        if self._docker_path is None:
            logger.warning("Docker CLI not available on PATH")
            return False
        return True

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------
    def check_docker_status(self) -> Dict[str, str]:
        """Return a high-level status message for the Docker daemon."""
        if not self._ensure_docker_available():
            return {
                "status": "Not Installed",
                "message": "Docker executable not found on PATH",
            }

        # Prefer systemd if available
        try:
            systemctl = shutil.which("systemctl")
            if systemctl:
                result = self._run([systemctl, "is-active", "docker"])
                if result.returncode == 0:
                    return {"status": "Running", "message": "Docker service is active"}
                return {
                    "status": "Not Running",
                    "message": result.stdout.strip() or "Docker service is inactive",
                }
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug("systemctl status check failed", exc_info=exc)

        # Fallback: `docker info`
        result = self._run([self._docker_path, "info"])
        if result.returncode == 0:
            return {"status": "Running", "message": "Docker daemon reachable"}

        logger.error(
            "Docker info command failed",
            extra={"returncode": result.returncode, "stderr": result.stderr.strip()},
        )
        return {
            "status": "Not Running",
            "message": result.stderr.strip() or "Docker daemon is not responding",
        }

    def get_running_containers(self) -> Dict[str, Optional[List[Dict[str, str]]]]:
        """Return a JSON-serialisable structure describing running containers."""
        if not self._ensure_docker_available():
            return {
                "status": "error",
                "containers": None,
                "message": "Docker is not installed",
            }

        format_arg = "{{json .}}"
        result = self._run([self._docker_path, "ps", "--format", format_arg])
        if result.returncode != 0:
            logger.error(
                "Failed to list docker containers",
                extra={"returncode": result.returncode, "stderr": result.stderr.strip()},
            )
            return {
                "status": "error",
                "containers": None,
                "message": result.stderr.strip() or "Error running docker ps",
            }

        containers: List[Dict[str, str]] = []
        for line in result.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                payload: Dict[str, Any] = json.loads(line)
            except json.JSONDecodeError:
                logger.warning("Unable to parse docker ps output line", extra={"line": line})
                continue

            containers.append(
                {
                    "id": payload.get("ID", ""),
                    "name": payload.get("Names", ""),
                    "status": payload.get("Status", ""),
                    "image": payload.get("Image", ""),
                }
            )

        if not containers:
            return {
                "status": "success",
                "containers": None,
                "message": "No containers are currently running",
            }

        return {"status": "success", "containers": containers, "message": ""}

    # ------------------------------------------------------------------
    # legacy interactive helper (kept for compatibility)
    # ------------------------------------------------------------------
    def view_docker_containers(self) -> None:
        """Print running container information to stdout for legacy menus."""
        try:
            from .utils import Colors, print_header, pause
        except Exception:  # pragma: no cover - optional dependency
            logger.error("Legacy console utilities unavailable; cannot render view")
            return

        print_header("Docker Containers")
        result = self.get_running_containers()

        if result["status"] == "error":
            print(f"{Colors.RED}{result['message']}{Colors.NC}")
        elif not result["containers"]:
            print("- No containers are currently running.")
        else:
            print("Active containers:")
            for container in result["containers"] or []:
                print(f"ID: {container['id']}")
                print(f"Name: {container['name']}")
                print(f"Status: {container['status']}")
                if container.get("image"):
                    print(f"Image: {container['image']}")
                print("-" * 30)

        pause()


# Preserve historical name
DockerManager = DockerService

__all__ = ["DockerService", "DockerManager"]
