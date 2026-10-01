"""Results paging at the bottom of the search results page."""

from __future__ import annotations

from playwright.sync_api import Page

from core.base_page import BasePage
from core.config import Settings
from utils.urls import query_param

PAGE_PARAM = "_pgn"


class Pagination(BasePage):
    def __init__(self, page: Page, settings: Settings) -> None:
        super().__init__(page, settings)
        # On the last page "next" is missing or rendered disabled, without a link.
        self.next_link = page.locator("nav.pagination a.pagination__next[href]:not([aria-disabled='true'])")

    @property
    def current_page(self) -> int:
        return int(query_param(self.page.url, PAGE_PARAM) or 1)

    def has_next(self) -> bool:
        return self.next_link.count() > 0

    def go_next(self) -> None:
        target = self.current_page + 1
        self.log.info("Going to results page %d", target)
        self.click(self.next_link)
        self.wait_for_navigation(lambda url: query_param(url, PAGE_PARAM) == str(target))
