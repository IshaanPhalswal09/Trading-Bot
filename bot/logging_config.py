"""
Centralised logging configuration.

- INFO+ to console (clean, human-readable)
- DEBUG+ to rotating file (full detail for auditing)
"""

import logging
import logging.handlers
import os
from pathlib import Path

LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
LOG_FILE = LOG_DIR / "trading_bot.log"
MAX_BYTES = 5 * 1024 * 1024  # 5 MB per file
BACKUP_COUNT = 3

_configured = False


def setup_logging(verbose: bool = False) -> None:
    global _configured
    if _configured:
        return

    LOG_DIR.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    # ------------------------------------------------------------------
    # File handler – DEBUG level, rotating
    # ------------------------------------------------------------------
    file_fmt = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    file_handler = logging.handlers.RotatingFileHandler(
        LOG_FILE,
        maxBytes=MAX_BYTES,
        backupCount=BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(file_fmt)
    root.addHandler(file_handler)

    # ------------------------------------------------------------------
    # Console handler – INFO (or DEBUG if verbose)
    # ------------------------------------------------------------------
    console_fmt = logging.Formatter(
        fmt="%(levelname)-8s %(message)s",
    )
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG if verbose else logging.WARNING)
    console_handler.setFormatter(console_fmt)
    root.addHandler(console_handler)

    # Quieten noisy third-party libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    _configured = True


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
