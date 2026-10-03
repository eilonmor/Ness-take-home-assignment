"""Results paging at the bottom of the search results page."""

from __future__ import annotations

from playwright.sync_api import Page

from core.base_page import BasePage
from core.config import Settings
from core.constants import FIRST_PAGE, QueryParam
from core.constants import PaginationLocators as Locators
from utils.urls import query_param


class Pagination(BasePage):
    def __init__(self, page: Page, settings: Settings) -> None:
        super().__init__(page, settings)
        self.next_link = page.locator(Locators.NEXT_LINK)

    @property
    def current_page(self) -> int:
        return int(query_param(self.page.url, QueryParam.PAGE) or FIRST_PAGE)

    def has_next(self) -> bool:
        return self.next_link.count() > 0

    def go_next(self) -> None:
        target = self.current_page + 1
        self.log.info("Going to results page %d", target)
        with self.expect_navigation(lambda url: query_param(url, QueryParam.PAGE) == str(target)):
            self.click(self.next_link)
