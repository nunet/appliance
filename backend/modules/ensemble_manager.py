"""
Compatibility wrapper for the deprecated `EnsembleManager` implementation.
The menu-driven version has been superseded by :class:`EnsembleService` which
exposes a clean API surface for FastAPI endpoints and utilities.
"""

from __future__ import annotations

from .ensemble_service import EnsembleService

EnsembleManager = EnsembleService

__all__ = ["EnsembleManager", "EnsembleService"]


