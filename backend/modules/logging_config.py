"""
Central logging configuration for NuNet backend modules.
"""

from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path
from typing import Optional

try:
    import colorama
except Exception:  # pragma: no cover - optional dependency
    colorama = None

_LOG_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
_DEFAULT_LOG_DIR = Path.home() / "nunet" / "appliance" / "logs"
_DEFAULT_LOG_FILE = "appliance.log"

_COLOR_MAP = {
    logging.DEBUG: "\033[34m",     # blue
    logging.INFO: "\033[32m",      # green
    logging.WARNING: "\033[33m",   # yellow
    logging.ERROR: "\033[31m",     # red
    logging.CRITICAL: "\033[35m",  # magenta
}
_RESET = "\033[0m"


class ColorFormatter(logging.Formatter):
    def __init__(self, fmt: str, datefmt: Optional[str] = None, use_color: bool = True) -> None:
        super().__init__(fmt, datefmt)
        self.use_color = use_color

    def format(self, record: logging.LogRecord) -> str:  # pragma: no cover - formatting logic
        levelname = record.levelname
        if self.use_color and record.levelno in _COLOR_MAP:
            record.levelname = f"{_COLOR_MAP[record.levelno]}{levelname}{_RESET}"
        try:
            return super().format(record)
        finally:
            record.levelname = levelname


_configured = False


def setup_logging(level: int = logging.INFO, log_dir: Optional[Path] = None) -> None:
    """Configure root logging handlers once."""
    global _configured
    if _configured:
        return

    if colorama is not None:  # pragma: no branch - best effort enable colors on Windows
        try:
            colorama.init()
        except Exception:
            pass

    log_dir = (log_dir or _DEFAULT_LOG_DIR).expanduser()
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / _DEFAULT_LOG_FILE

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()

    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_handler.setFormatter(ColorFormatter(_LOG_FORMAT, _DATE_FORMAT, use_color=True))

    file_handler = logging.handlers.RotatingFileHandler(
        log_file,
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(logging.Formatter(_LOG_FORMAT, _DATE_FORMAT))

    root.addHandler(console_handler)
    root.addHandler(file_handler)

    # Keep third-party loggers chatty enough but not noisy
    logging.getLogger("uvicorn").setLevel(logging.INFO)
    logging.getLogger("uvicorn.error").setLevel(logging.INFO)
    logging.getLogger("uvicorn.access").setLevel(logging.INFO)

    _configured = True


def get_logger(name: str) -> logging.Logger:
    """Return a logger with the shared configuration."""
    setup_logging()
    return logging.getLogger(name)
