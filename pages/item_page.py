"""eBay item page (/itm/<id>): variants, quantity and "Add to cart"."""

from __future__ import annotations

import random
from typing import Self

from playwright.sync_api import Page
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from components.added_to_cart_dialog import AddedToCartDialog
from components.header import Header
from components.variant_selector import VariantChoice, VariantSelector
from core.base_page import BasePage
from core.config import Settings
from core.exceptions import AddToCartError, VariantSelectionError

# The "Add to cart" link points here; it is followed only when the click lands
# before the page's scripts take it over (then eBay shows the cart page instead
# of the dialog, but the item is added all the same).
CART_URL_PARTS = ("cart.ebay.", "cart.payments.ebay.")


class ItemPage(BasePage):
    def __init__(self, page: Page, settings: Settings) -> None:
        super().__init__(page, settings)
        self.header = Header(page, settings)
        self.variants = VariantSelector(page, settings)
        self.added_dialog = AddedToCartDialog(page, settings)
        self.title = page.locator("h1.x-item-title__mainTitle")
        self.price = page.locator("[data-testid='x-price-primary']").first
        self.quantity_input = page.locator("[data-testid='x-quantity'] input[name='quantity']")
        self.add_to_cart_button = page.locator("[data-testid='x-atc-action'] a.ux-call-to-action")

    def open_listing(self, url: str) -> Self:
        self.path = url
        self.open()
        self.header.dismiss_ship_to_dialog()
        self.wait_until_visible(self.title)
        return self

    def title_text(self) -> str:
        return self.text_of(self.title)

    def price_text(self) -> str:
        """As displayed, e.g. "US $16.25" or "ILS 59.37"; changes with the chosen variant."""
        return self.text_of(self.price) if self.price.count() else "n/a"

    def select_random_variants(self, rng: random.Random) -> list[VariantChoice]:
        if not self.variants.has_variants():
            self.log.info("No variants to pick")
            return []
        return self.variants.select_random(rng)

    def keep_quantity_at_one(self) -> None:
        """One unit per item, so the cart total stays comparable to budget * item count.

        The box is disabled when only one unit is for sale ("Last one").
        """
        box = self.quantity_input
        if box.count() and box.is_enabled() and box.input_value() != "1":
            self.log.info("Setting quantity to 1 (was %s)", box.input_value())
            self.fill(box, "1")

    def add_to_cart(self) -> str:
        """Click "Add to cart" and wait until eBay confirms; returns the confirmation text.

        The confirmation dialog is left open (it makes a good screenshot);
        close it with ``added_dialog.close()`` before clicking anything else.

        Raises ``AddToCartError`` when the listing has no "Add to cart" (ended,
        auction only), when a variant is still unselected, or when eBay shows
        neither the dialog nor the cart.
        """
        if not self.is_visible(self.add_to_cart_button):
            raise AddToCartError(
                f"No 'Add to cart' button on {self.url} (listing ended, sold out or auction only?)"
            )
        # Clicked before the page's scripts are ready, the link navigates away instead of opening the dialog.
        self.page.wait_for_load_state("load")
        self.click(self.add_to_cart_button)

        outcome = self.added_dialog.details.or_(self.variants.missing_value_errors).first
        try:
            outcome.wait_for(state="visible")
        except PlaywrightTimeoutError:
            if any(part in self.url for part in CART_URL_PARTS):
                self.ensure_not_blocked()
                self.log.info("eBay opened the cart page instead of the dialog")
                return "Opened the cart page"
            raise AddToCartError(f"eBay did not confirm the add to cart on {self.url}") from None

        if missing := self.variants.missing_values():
            raise VariantSelectionError(f"eBay asks to select: {', '.join(missing)}")
        return self.added_dialog.summary()
