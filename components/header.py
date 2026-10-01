"""eBay global header (``#gh``), shared by the home, search and item pages."""

from __future__ import annotations

from playwright.sync_api import Page

from core.base_page import BasePage
from core.config import Settings


class Header(BasePage):
    """Sign-in state and the "Are you shipping to ...?" dialog.

    CSS, not role locators: while the ship-to dialog is open eBay marks the
    rest of the header ``aria-hidden``, so ``get_by_role("link", name="Sign in")``
    finds nothing.
    """

    def __init__(self, page: Page, settings: Settings) -> None:
        super().__init__(page, settings)
        self.root = page.locator("#gh")
        self.identity = self.root.locator(".gh-identity")
        # Guest: <span class="gh-identity-signed-out-unrecognized">Hi! <a>Sign in</a> or <a>register</a>
        self.signed_out_marker = self.identity.locator("[class*='signed-out']")
        self.sign_in_link = self.identity.locator("a[href*='signin.ebay.']")
        self.ship_to_dialog = self.root.locator(".address-dialog__lightbox")
        self.ship_to_dismiss = self.ship_to_dialog.locator("button.lightbox-dialog__close")
        self.search_input = self.root.locator("#gh-ac")
        self.search_button = self.root.locator("#gh-search-btn")

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
        self.click(self.search_button)
        self.wait_for_navigation(lambda url: "/sch/" in url)

    def dismiss_ship_to_dialog(self) -> None:
        """Close the modal that asks to confirm the shipping postcode; it blocks every click."""
        if not self.is_visible(self.ship_to_dialog):
            return
        self.log.info("Dismissing the ship-to dialog")
        self.click(self.ship_to_dismiss)
        self.ship_to_dialog.wait_for(state="hidden")
