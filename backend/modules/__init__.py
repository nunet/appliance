"""
NuNet Appliance Management System Modules.
"""

from __future__ import annotations

import sys
from pathlib import Path

_MODULES_DIR = Path(__file__).resolve().parent
_BACKEND_DIR = _MODULES_DIR.parent
_REPO_ROOT = _BACKEND_DIR.parent

# Ensure the repository root is on sys.path so `import backend` works even when
# Python is executed from backend/.
_repo_str = str(_REPO_ROOT)
if _repo_str not in sys.path:
    sys.path.append(_repo_str)

from .path_constants import ADMIN_CREDENTIALS_PATH

__all__ = ["ADMIN_CREDENTIALS_PATH"]
