"""
Utility helpers for organisation onboarding flows exposed via FastAPI.

Only the script-backed wormhole generation/join logic is preserved; all menu
specific presentation code has been removed.
"""

import logging
import subprocess
from pathlib import Path
from typing import Dict, Optional

from .org_utils import get_joined_organizations_with_names, load_known_organizations

logger = logging.getLogger(__name__)

JOIN_SCRIPT = "join-org-web.sh"


class OrganizationManager:
    def __init__(self, scripts_dir: Optional[Path] = None) -> None:
        self.scripts_dir = scripts_dir or (Path.home() / "menu" / "scripts")

    # ------------------------------------------------------------------ #
    # Script helpers
    # ------------------------------------------------------------------ #

    def _script_path(self) -> Path:
        candidate = self.scripts_dir / JOIN_SCRIPT
        if candidate.exists():
            return candidate
        repo_scripts = Path(__file__).resolve().parents[1] / "scripts"
        alt = repo_scripts / JOIN_SCRIPT
        return alt

    def _run_script(self, *args: str) -> Dict[str, str]:
        script = self._script_path()
        if not script.exists():
            location = script if script == self.scripts_dir / JOIN_SCRIPT else script.resolve()
            return {"status": "error", "message": f"Organization join script not found at {location}"}

        try:
            cp = subprocess.run(
                ["bash", str(script), *args],
                capture_output=True,
                text=True,
                check=False,
            )
        except FileNotFoundError:
            logger.exception("bash executable not available while running %s", script)
            return {"status": "error", "message": "bash executable not available"}

        stdout = cp.stdout or ""
        stderr = cp.stderr or ""
        output = (stdout + stderr).strip()

        if cp.returncode != 0:
            logger.warning("join-org script failed (%s): %s", cp.returncode, output)
            return {
                "status": "error",
                "message": stderr.strip() or stdout.strip() or f"Exited with {cp.returncode}",
                "output": output,
            }

        return {"status": "success", "message": stdout.strip() or "completed", "output": output}

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def join_organization(
        self,
        org_type: Optional[str] = None,
        step: str = "generate",
        code: Optional[str] = None,
        **_extras: str,
    ) -> Dict[str, str]:
        """
        Run the legacy join-org script in a controlled way.

        Parameters mirror the historical implementation so the FastAPI layer can
        keep its contract.
        """
        step = step or "generate"

        if step not in {"generate", "join"}:
            return {"status": "error", "message": f"Unsupported step: {step}"}

        if step == "join" and not code:
            return {"status": "error", "message": "Wormhole code is required for join step."}

        args = [step]
        if step == "join" and code:
            args.append(code)

        result = self._run_script(*args)
        if result.get("status") != "success":
            return result

        # The generate step prints the wormhole code on stdout; expose it explicitly.
        if step == "generate":
            wormhole = result.get("message", "").splitlines()[-1].strip()
            result["wormhole_code"] = wormhole
            if org_type:
                result["organization"] = org_type

        return result

    def get_organization_status(self) -> Dict[str, object]:
        """Expose joined/known organisation data expected by the API."""
        return {
            "joined": get_joined_organizations_with_names(),
            "known": load_known_organizations(),
        }
