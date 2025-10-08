"""
Legacy wrapper for the organization service.
"""

from __future__ import annotations

from .organization_service import OrganizationService, OrganizationType

# Backward compatibility: existing imports of OrganizationManager continue to work.
OrganizationManager = OrganizationService

__all__ = ["OrganizationManager", "OrganizationService", "OrganizationType"]
