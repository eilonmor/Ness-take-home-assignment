"""The "Added to cart" overlay an item page opens after "Add to cart"."""

from __future__ import annotations

from playwright.sync_api import Page

from core.base_page import BasePage
from core.config import Settings
from core.constants import AddedToCartDialogLocators as Locators


class AddedToCartDialog(BasePage):
    """Shows a spinner ("Adding to your cart"), then the item and "See in cart".

    It covers the page, so it is closed before anything else is clicked.
    """

    def __init__(self, page: Page, settings: Settings) -> None:
        super().__init__(page, settings)
        self.root = page.locator(Locators.ROOT)
        self.details = self.root.locator(Locators.DETAILS)
        self.close_button = self.root.locator(Locators.CLOSE_BUTTON)

    def summary(self) -> str:
        """e.g. "Unisex classic tee / M, White / ILS 59.37 / See in cart ..."."""
        return " / ".join(line.strip() for line in self.text_of(self.details).splitlines() if line.strip())

    def close(self) -> None:
        if not self.root.is_visible():
            return
        self.log.debug("Closing the added-to-cart dialog")
        self.click(self.close_button)
        self.root.wait_for(state="hidden")
