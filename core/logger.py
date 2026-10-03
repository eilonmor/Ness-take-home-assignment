"""Project-wide logging: one console handler and one file handler per run."""

from __future__ import annotations

import logging
from pathlib import Path

from core.constants import Logging


def configure_logging(log_dir: Path, level: str = Logging.DEFAULT_LEVEL) -> Path:
    """Attach console + file handlers to the project root logger (idempotent).

    Returns the path of the log file.
    """
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / Logging.FILE_NAME

    root = logging.getLogger(Logging.ROOT_LOGGER)
    root.setLevel(level)
    if root.handlers:
        return log_file

    formatter = logging.Formatter(Logging.FORMAT)

    console = logging.StreamHandler()
    console.setFormatter(formatter)
    root.addHandler(console)

    file_handler = logging.FileHandler(log_file, mode="w", encoding="utf-8")
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    return log_file


def get_logger(name: str) -> logging.Logger:
    """Child of the project root logger, e.g. ``ness.SearchResultsPage``."""
    return logging.getLogger(f"{Logging.ROOT_LOGGER}.{name}")
