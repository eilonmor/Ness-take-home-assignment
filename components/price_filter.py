"""The "Price" min/max box in the search results sidebar."""

from __future__ import annotations

import math

from playwright.sync_api import Page

from core.base_page import BasePage
from core.config import Settings
from core.constants import PriceFilterLocators as Locators
from core.constants import QueryParam
from utils.urls import query_param


class PriceFilter(BasePage):
    """Narrows the results to a maximum price, in the currency eBay displays.

    The placeholder names the currency ("Max ILS", "Max $"), so the input is
    found by its "Max" prefix rather than by the full, region-dependent label.
    """

    def __init__(self, page: Page, settings: Settings) -> None:
        super().__init__(page, settings)
        self.section = page.locator(Locators.SECTION).filter(has=page.locator(Locators.MAX_INPUT)).first
        self.max_input = self.section.locator(Locators.MAX_INPUT)
        self.submit_button = self.section.locator(Locators.SUBMIT_BUTTON)

    def is_available(self) -> bool:
        return self.is_visible(self.max_input)

    def apply_max(self, max_price: float) -> None:
        # The box takes whole numbers only (pattern="\d*"). Rounding up keeps
        # every matching item; the exact <= check is done per card afterwards.
        value = str(math.ceil(max_price))
        self.log.info("Applying the price filter: max %s", value)
        self.fill(self.max_input, value)
        # eBay navigates a moment after the click, to a URL with _udhi=<value>.
        with self.expect_navigation(lambda url: query_param(url, QueryParam.MAX_PRICE) == value):
            self.click(self.submit_button)
