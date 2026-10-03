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
