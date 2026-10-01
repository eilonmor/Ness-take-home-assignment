"""eBay home page: the entry point of every session."""

from __future__ import annotations

from typing import Self

from playwright.sync_api import Page

from components.header import Header
from core.base_page import BasePage
from core.config import Settings


class HomePage(BasePage):
    path = "/"

    def __init__(self, page: Page, settings: Settings) -> None:
        super().__init__(page, settings)
        self.header = Header(page, settings)

    def open(self) -> Self:
        super().open()
        self.header.dismiss_ship_to_dialog()
        return self
