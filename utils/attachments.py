"""Attach artifacts (screenshots, traces, logs) to the Allure report."""

from __future__ import annotations

from pathlib import Path

import allure

from core.constants import ArtifactFiles, AttachmentName


def attach_screenshot(path: Path, name: str) -> None:
    allure.attach.file(str(path), name=name, attachment_type=allure.attachment_type.PNG)


def attach_trace(path: Path, name: str = AttachmentName.TRACE) -> None:
    # Open locally with: playwright show-trace <file>.zip
    allure.attach.file(str(path), name=name, extension=ArtifactFiles.TRACE_ATTACHMENT_EXTENSION)


def attach_text(content: str, name: str) -> None:
    allure.attach(content, name=name, attachment_type=allure.attachment_type.TEXT)


def write_allure_environment(results_dir: Path, values: dict[str, str]) -> Path:
    """Write the run's settings for the "Environment" widget of the Allure report."""
    path = results_dir / ArtifactFiles.ALLURE_ENVIRONMENT
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = (f"{_escape_key(key)}={_escape_value(value)}\n" for key, value in values.items())
    path.write_text("".join(lines), encoding="utf-8")
    return path


def _escape_value(text: str) -> str:
    # Java .properties: backslash is the escape character.
    return text.replace("\\", "\\\\")


def _escape_key(text: str) -> str:
    # A space, '=' or ':' would end the key early.
    escaped = _escape_value(text)
    for char in " =:":
        escaped = escaped.replace(char, f"\\{char}")
    return escaped
