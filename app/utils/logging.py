"""Central logging configuration."""
from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .paths import app_log_dir

_CONFIGURED = False
LOG_NAME = "pubg_autoclips"


def get_logger(name: str | None = None) -> logging.Logger:
    global _CONFIGURED
    if not _CONFIGURED:
        _configure()
    return logging.getLogger(LOG_NAME + (("." + name) if name else ""))


def _configure() -> None:
    global _CONFIGURED
    logger = logging.getLogger(LOG_NAME)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    if logger.handlers:
        _CONFIGURED = True
        return

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    try:
        log_dir: Path = app_log_dir()
        log_dir.mkdir(parents=True, exist_ok=True)
        fh = RotatingFileHandler(
            log_dir / "pubg_autoclips.log", maxBytes=2_000_000,
            backupCount=5, encoding="utf-8",
        )
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(fmt)
        logger.addHandler(fh)
    except Exception:
        pass  # Logging to file is best-effort; never block startup.

    sh = logging.StreamHandler(sys.stderr)
    sh.setLevel(logging.INFO)
    sh.setFormatter(fmt)
    logger.addHandler(sh)
    _CONFIGURED = True
