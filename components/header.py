"""eBay global header (``#gh``), shared by the home, search and item pages."""

from __future__ import annotations

from playwright.sync_api import Page

from core.base_page import BasePage
from core.config import Settings
from core.constants import Endpoints
from core.constants import HeaderLocators as Locators


class Header(BasePage):
    """Sign-in state and the "Are you shipping to ...?" dialog.

    CSS, not role locators: while the ship-to dialog is open eBay marks the
    rest of the header ``aria-hidden``, so ``get_by_role("link", name="Sign in")``
    finds nothing.
    """

    def __init__(self, page: Page, settings: Settings) -> None:
        super().__init__(page, settings)
        self.root = page.locator(Locators.ROOT)
        self.identity = self.root.locator(Locators.IDENTITY)
        self.signed_out_marker = self.identity.locator(Locators.SIGNED_OUT_MARKER)
        self.sign_in_link = self.identity.locator(Locators.SIGN_IN_LINK)
        self.ship_to_dialog = self.root.locator(Locators.SHIP_TO_DIALOG)
        self.ship_to_dismiss = self.ship_to_dialog.locator(Locators.SHIP_TO_DISMISS)
        self.search_input = self.root.locator(Locators.SEARCH_INPUT)
        self.search_button = self.root.locator(Locators.SEARCH_BUTTON)
        self.cart_badge = self.root.locator(Locators.CART_BADGE)

    def is_signed_in(self) -> bool:
        self.wait_until_visible(self.identity)
        return self.signed_out_marker.count() == 0

    def greeting(self) -> str:
        """e.g. "Hi! Sign in or register" for a guest."""
        return self.text_of(self.identity)

    def click_sign_in(self) -> None:
        self.log.info("Opening the sign-in page")
        self.click(self.sign_in_link)

    def search(self, query: str) -> None:
        """Submit the header search box and wait for the results page.

        Searching from a page eBay already served is the supported way in: a
        cold deep link to /sch/... is answered with a bot check.
        """
        self.dismiss_ship_to_dialog()
        self.log.info("Searching for %r", query)
        self.fill(self.search_input, query)
        with self.expect_navigation(lambda url: Endpoints.SEARCH_PATH_PART in url):
            self.click(self.search_button)

    def cart_count(self) -> int:
        if self.cart_badge.count() == 0:
            return 0
        return _badge_count(self.cart_badge.inner_text())

    def wait_for_cart_count_above(self, count: int) -> int:
        """Wait until the badge shows more than ``count`` items (it updates in place after an add)."""
        self.page.wait_for_function(
            "([selector, count]) => parseInt(document.querySelector(selector)?.textContent ?? '0', 10) > count",
            arg=[f"{Locators.ROOT} {Locators.CART_BADGE}", count],
        )
        return self.cart_count()

    def dismiss_ship_to_dialog(self) -> None:
        """Close the modal that asks to confirm the shipping postcode; it blocks every click."""
        if not self.is_visible(self.ship_to_dialog):
            return
        self.log.info("Dismissing the ship-to dialog")
        self.click(self.ship_to_dismiss)
        self.ship_to_dialog.wait_for(state="hidden")


def _badge_count(text: str) -> int:
    """Badge text is a count, possibly capped like "99+"."""
    digits = "".join(char for char in text.strip() if char.isdigit())
    return int(digits) if digits else 0
