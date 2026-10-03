"""eBay sign-in page (signin.ebay.com): username first, then password."""

from __future__ import annotations

from playwright.sync_api import Locator, Page
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from components.header import Header
from core.base_page import BasePage
from core.config import Settings
from core.constants import EnvVar
from core.constants import LoginPageLocators as Locators
from core.exceptions import LoginError


class LoginPage(BasePage):
    """Opened from the header link, so eBay returns to the home page after sign-in."""

    def __init__(self, page: Page, settings: Settings) -> None:
        super().__init__(page, settings)
        self.username_input = page.locator(Locators.USERNAME_INPUT)
        self.continue_button = page.locator(Locators.CONTINUE_BUTTON)
        self.password_input = page.locator(Locators.PASSWORD_INPUT)
        self.sign_in_button = page.locator(Locators.SIGN_IN_BUTTON)
        self.error_message = page.locator(Locators.ERROR_MESSAGE)
        # Present once eBay redirects back to www.ebay.com; not on the sign-in page.
        self.home_header = Header(page, settings).identity

    def sign_in(self, username: str, password: str) -> None:
        self.log.info("Signing in as %s", username)
        self._wait_for(self.username_input, step="sign-in form")
        self.fill(self.username_input, username)
        self.click(self.continue_button)

        self._wait_for(self.password_input, step="username")
        self.fill(self.password_input, password)
        self.click(self.sign_in_button)

        self._wait_for(self.home_header, step="password")

    def _wait_for(self, expected: Locator, step: str) -> None:
        """Wait for the next step, turning an inline error or a captcha into a clear exception."""
        try:
            expected.or_(self.error_message).first.wait_for(state="visible")
        except PlaywrightTimeoutError:
            self.ensure_not_blocked()
            raise LoginError(
                f"Sign-in stopped after the {step} step at {self.page.url} "
                f"(likely an extra check such as 2FA or a passkey prompt). Use guest mode: {EnvVar.GUEST}=true."
            ) from None
        if self.error_message.is_visible():
            raise LoginError(f"eBay rejected the {step}: {self.error_message.inner_text().strip()}")
