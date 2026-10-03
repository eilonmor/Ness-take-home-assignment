"""Evidence for the pytest-html report (reports/report.html): embedded screenshots, trace links."""

from __future__ import annotations

import base64
import os
from pathlib import Path
from typing import Any

from pytest_html import extras


def screenshot_extra(path: Path, name: str) -> list[Any]:
    # Embedded, so the report stays one self-contained file.
    return [extras.png(base64.b64encode(path.read_bytes()).decode("ascii"), name=name)]


def trace_extra(path: Path, report_file: Path | None, name: str) -> list[Any]:
    # A link relative to the report; too big to embed.
    if report_file is None:
        return []
    return [extras.url(Path(os.path.relpath(path, report_file.parent)).as_posix(), name=name)]
