"""The "Price" min/max box in the search results sidebar."""

from __future__ import annotations

import math

from playwright.sync_api import Page

from core.base_page import BasePage
from core.config import Settings
from utils.urls import query_param

MAX_PRICE_PARAM = "_udhi"


class PriceFilter(BasePage):
    """Narrows the results to a maximum price, in the currency eBay displays.

    The placeholder names the currency ("Max ILS", "Max $"), so the input is
    found by its "Max" prefix rather than by the full, region-dependent label.
    """

    def __init__(self, page: Page, settings: Settings) -> None:
        super().__init__(page, settings)
        max_input = "input[placeholder^='Max']"
        self.section = page.locator(".su-price-filter__section").filter(has=page.locator(max_input)).first
        self.max_input = self.section.locator(max_input)
        self.submit_button = self.section.locator("button.su-textrange__submit-button")

    def is_available(self) -> bool:
        return self.is_visible(self.max_input)

    def apply_max(self, max_price: float) -> None:
        # The box takes whole numbers only (pattern="\d*"). Rounding up keeps
        # every matching item; the exact <= check is done per card afterwards.
        value = str(math.ceil(max_price))
        self.log.info("Applying the price filter: max %s", value)
        self.fill(self.max_input, value)
        # eBay navigates a moment after the click, to a URL with _udhi=<value>.
        with self.expect_navigation(lambda url: query_param(url, MAX_PRICE_PARAM) == value):
            self.click(self.submit_button)
