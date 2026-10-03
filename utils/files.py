"""Helpers for naming artifact files."""

from __future__ import annotations

import re
from datetime import datetime

from core.constants import Files

_UNSAFE_CHARS = re.compile(r"[^A-Za-z0-9._-]+")


def safe_filename(name: str, max_length: int = Files.MAX_NAME_LENGTH) -> str:
    """Turn any label (test id, item title) into a file-system safe name."""
    cleaned = _UNSAFE_CHARS.sub("_", name).strip("._")
    return cleaned[:max_length] or Files.FALLBACK_NAME


def timestamp() -> str:
    return datetime.now().strftime(Files.TIMESTAMP_FORMAT)[:-3]  # microseconds -> milliseconds
