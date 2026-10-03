"""The "Added to cart" overlay an item page opens after "Add to cart"."""

from __future__ import annotations

from playwright.sync_api import Page

from core.base_page import BasePage
from core.config import Settings


class AddedToCartDialog(BasePage):
    """Shows a spinner ("Adding to your cart"), then the item and "See in cart".

    It covers the page, so it is closed before anything else is clicked.
    """

    def __init__(self, page: Page, settings: Settings) -> None:
        super().__init__(page, settings)
        self.root = page.locator(".x-atc-action__overlay")
        # Only rendered once the item is in the cart (the spinner state has no details).
        self.details = self.root.locator(".x-atc-layer-v3--info")
        self.close_button = self.root.locator("button.lightbox-dialog__close")

    def summary(self) -> str:
        """e.g. "Unisex classic tee / M, White / ILS 59.37 / See in cart ..."."""
        return " / ".join(line.strip() for line in self.text_of(self.details).splitlines() if line.strip())

    def close(self) -> None:
        if not self.root.is_visible():
            return
        self.log.debug("Closing the added-to-cart dialog")
        self.click(self.close_button)
        self.root.wait_for(state="hidden")
