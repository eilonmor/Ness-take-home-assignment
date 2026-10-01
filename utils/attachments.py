"""Attach artifacts (screenshots, traces, logs) to the Allure report."""

from __future__ import annotations

from pathlib import Path

import allure


def attach_screenshot(path: Path, name: str) -> None:
    allure.attach.file(str(path), name=name, attachment_type=allure.attachment_type.PNG)


def attach_trace(path: Path, name: str = "Playwright trace") -> None:
    # Open locally with: playwright show-trace <file>.zip
    allure.attach.file(str(path), name=name, extension="zip")


def attach_text(content: str, name: str) -> None:
    allure.attach(content, name=name, attachment_type=allure.attachment_type.TEXT)
