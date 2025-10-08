"""
Backward compatibility shim for legacy imports of `modules.ensemble_manager_v2`.
The interactive menu implementation has been replaced by the API-focused
`EnsembleService`. Import `EnsembleService` for new code; existing modules can
continue to use `EnsembleManagerV2` as an alias.
"""

from __future__ import annotations

import warnings
from pathlib import Path
from typing import Any

from .ensemble_service import EnsembleService
from .logging_config import get_logger

logger = get_logger(__name__)


class EnsembleManagerV2(EnsembleService):
    """Deprecated wrapper that forwards to :class:`EnsembleService`."""

    _POSITIONAL_MAP = ("base_dir", "log_dir", "deployments_dir")

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        if args:
            warnings.warn(
                "EnsembleManagerV2 positional arguments are deprecated; use keyword arguments instead.",
                DeprecationWarning,
                stacklevel=2,
            )
            for key, value in zip(self._POSITIONAL_MAP, args):
                if key not in kwargs and value is not None:
                    kwargs[key] = Path(value)

        warnings.warn(
            "EnsembleManagerV2 is deprecated and will be removed in a future release. "
            "Import modules.ensemble_service.EnsembleService instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        logger.debug(
            "EnsembleManagerV2 initialised; delegating to EnsembleService",
            extra={"has_args": bool(args), "has_kwargs": bool(kwargs)},
        )
        super().__init__(**kwargs)


__all__ = ["EnsembleManagerV2", "EnsembleService"]
