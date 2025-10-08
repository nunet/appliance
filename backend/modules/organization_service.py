"""
Service layer for organization onboarding operations.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Dict, Literal, Optional

from .logging_config import get_logger
from .org_utils import (
    get_joined_organizations_with_names,
    load_known_organizations,
)

OrganizationType = Literal["nunet", "auki", "jam_galaxy", "ocean"]

logger = get_logger(__name__)


class OrganizationService:
    """Business logic for organization onboarding used by API controllers."""

    def __init__(self, scripts_dir: Optional[Path] = None) -> None:
        self.home_dir = Path.home()
        self.scripts_dir = scripts_dir or self.home_dir / "menu" / "scripts"
        logger.debug("OrganizationService initialized: scripts_dir=%s", self.scripts_dir)

    def join_organization(
        self,
        org_type: Optional[str] = None,
        step: str = "generate",
        code: Optional[str] = None,
        email: Optional[str] = None,
        location: Optional[str] = None,
        discord: Optional[str] = None,
        dms_did: Optional[str] = None,
        peer_id: Optional[str] = None,
    ) -> Dict[str, str]:
        """Run the legacy join-org-web.sh helper in generate or join mode."""
        logger.debug(
            "join_organization invoked: step=%s org_type=%s code_provided=%s",
            step,
            org_type,
            bool(code),
        )

        script_path = self.scripts_dir / "join-org-web.sh"
        if not script_path.exists():
            logger.error("Join script not found at %s", script_path)
            return {
                "status": "error",
                "message": "Organization join script for web not found",
            }

        try:
            if step == "generate":
                result = self._run_script(["bash", str(script_path), "generate"])
                output = self._combine_output(result)
                logger.debug(
                    "join-org-web.sh generate completed with rc=%s", result.returncode
                )
                if result.returncode == 0:
                    code_value = (result.stdout or "").strip()
                    logger.info("Generated wormhole code via %s", script_path)
                    logger.debug("join-org-web.sh generate output: %s", output.strip())
                    return {
                        "status": "success",
                        "wormhole_code": code_value,
                        "output": output,
                    }
                logger.error(
                    "join-org-web.sh generate failed rc=%s output=%s",
                    result.returncode,
                    output.strip(),
                )
                return {
                    "status": "error",
                    "message": (result.stderr or result.stdout or "").strip(),
                    "output": output,
                }

            if step == "join" and code:
                payload = {
                    "email": email,
                    "location": location,
                    "discord": discord,
                    "wormhole": code,
                    "dms_did": dms_did,
                    "peer_id": peer_id,
                }
                loggable_payload = dict(payload)
                if loggable_payload.get("wormhole"):
                    loggable_payload["wormhole"] = "***"
                logger.debug("join_organization join payload: %s", loggable_payload)

                result = self._run_script(["bash", str(script_path), "join", code])
                output = self._combine_output(result)
                logger.debug(
                    "join-org-web.sh join completed with rc=%s", result.returncode
                )
                if result.returncode == 0:
                    logger.info("Organization join process completed for %s", org_type)
                    logger.debug("join-org-web.sh join output: %s", output.strip())
                    return {
                        "status": "success",
                        "message": "Organization join process completed.",
                        "output": output,
                    }
                logger.error(
                    "join-org-web.sh join failed rc=%s output=%s",
                    result.returncode,
                    output.strip(),
                )
                return {
                    "status": "error",
                    "message": (
                        f"Failed to join organization. Process exited with code {result.returncode}"
                    ),
                    "output": output,
                }

            logger.warning("Invalid join step or missing code: step=%s code=%s", step, code)
            return {
                "status": "error",
                "message": "Invalid step or missing wormhole code.",
            }
        except Exception as exc:  # pragma: no cover - defensive guard
            logger.exception("Error joining organization")
            return {
                "status": "error",
                "message": f"Error joining organization: {exc}",
            }

    def get_organization_status(self) -> Dict[str, Dict[str, str]]:
        """Return joined and known organizations using org_utils helpers."""
        return {
            "joined": get_joined_organizations_with_names(),
            "known": load_known_organizations(),
        }

    @staticmethod
    def _run_script(args: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(args, capture_output=True, text=True, check=False)

    @staticmethod
    def _combine_output(result: subprocess.CompletedProcess[str]) -> str:
        stdout = result.stdout or ""
        stderr = result.stderr or ""
        return stdout + stderr


__all__ = ["OrganizationService", "OrganizationType"]
