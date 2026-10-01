"""Project-wide logging: one console handler and one file handler per run."""

from __future__ import annotations

import logging
from pathlib import Path

ROOT_LOGGER_NAME = "ness"
LOG_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
LOG_FILE_NAME = "run.log"


def configure_logging(log_dir: Path, level: str = "INFO") -> Path:
    """Attach console + file handlers to the project root logger (idempotent).

    Returns the path of the log file.
    """
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / LOG_FILE_NAME

    root = logging.getLogger(ROOT_LOGGER_NAME)
    root.setLevel(level)
    if root.handlers:
        return log_file

    formatter = logging.Formatter(LOG_FORMAT)

    console = logging.StreamHandler()
    console.setFormatter(formatter)
    root.addHandler(console)

    file_handler = logging.FileHandler(log_file, mode="w", encoding="utf-8")
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    return log_file


def get_logger(name: str) -> logging.Logger:
    """Child of the project root logger, e.g. ``ness.SearchResultsPage``."""
    return logging.getLogger(f"{ROOT_LOGGER_NAME}.{name}")
