"""
Logging setup for Jarvis v2 Core.

This module exposes a simple `get_logger` helper that you can use across
the project instead of configuring logging in each file separately.
"""

from __future__ import annotations

import logging
from logging import Logger
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

from .config import get_config
from .utils import get_project_root, ensure_directory


_configured: bool = False


def _configure_logging() -> None:
    """
    Configure the root logger.

    - Writes logs to `data/logs/jarvis.log`
    - Also logs to the console
    """
    global _configured
    if _configured:
        return

    project_root = get_project_root()
    logs_dir = project_root / "data" / "logs"
    ensure_directory(logs_dir)

    log_file = logs_dir / "jarvis.log"

    config = get_config()
    level = getattr(logging, config.log_level.upper(), logging.INFO)

    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
        handlers=[
            logging.StreamHandler(),
            RotatingFileHandler(
                filename=str(log_file),
                maxBytes=1_000_000,
                backupCount=3,
                encoding="utf-8",
            ),
        ],
    )

    _configured = True


def get_logger(name: Optional[str] = None) -> Logger:
    """
    Get a configured logger instance.

    Usage:
        from app.core.logger import get_logger
        logger = get_logger(__name__)
        logger.info("Hello from Jarvis!")
    """
    _configure_logging()
    return logging.getLogger(name)

