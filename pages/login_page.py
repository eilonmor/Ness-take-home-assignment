"""eBay sign-in page (signin.ebay.com): username first, then password."""

from __future__ import annotations

from typing import Self

from playwright.sync_api import Locator, Page
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from components.header import Header
from core.base_page import BasePage
from core.config import Settings
from core.constants import EnvVar, TraceMode
from core.constants import LoginPageLocators as Locators
from core.exceptions import LoginError
from utils.tracing import tracing_paused


class LoginPage(BasePage):
    """Opened from the header link, so eBay returns to the home page after sign-in.

    Two steps on one host: "Sign in to your account" (username, Continue) and
    "Welcome back!" (password, Sign in). ``submit_username`` / ``submit_password``
    stop at whatever eBay shows next, error included, so tests can check a
    rejection; ``sign_in`` raises ``LoginError`` on one instead.
    """

    def __init__(self, page: Page, settings: Settings) -> None:
        super().__init__(page, settings)
        self.username_input = page.locator(Locators.USERNAME_INPUT)
        self.continue_button = page.locator(Locators.CONTINUE_BUTTON)
        self.password_input = page.locator(Locators.PASSWORD_INPUT)
        self.sign_in_button = page.locator(Locators.SIGN_IN_BUTTON)
        self.error_message = page.locator(Locators.ERROR_MESSAGE)
        self.user_info = page.locator(Locators.USER_INFO)
        self.switch_account_link = page.locator(Locators.SWITCH_ACCOUNT)
        # Present once eBay redirects back to www.ebay.com; not on the sign-in page.
        self.home_header = Header(page, settings).identity

    def wait_until_loaded(self) -> Self:
        self._wait_for_step(self.username_input, step="sign-in link")
        return self

    def sign_in(self, username: str, password: str) -> None:
        self.log.info("Signing in as %s", username)
        self.wait_until_loaded()
        self.submit_username(username)
        self._raise_on_error(step="username")
        self.submit_password(password)
        self._raise_on_error(step="password")

    def submit_username(self, username: str) -> None:
        """Type the username and Continue; returns on the password step or an inline error."""
        self.fill(self.username_input, username)
        self.click(self.continue_button)
        self._wait_for_step(self.password_input, step="username")

    def submit_password(self, password: str) -> None:
        """Type the password and Sign in; returns on the eBay home page or an inline error.

        Not traced: the trace would store the password in plain text. eBay
        answers with a new page either way (the home page, or /signin/s with
        the error), so an error left from an earlier attempt is not mistaken
        for the answer to this one.
        """
        with tracing_paused(self.page.context, self.settings.artifacts.trace != TraceMode.OFF):
            self.fill(self.password_input, password)
            with self.expect_navigation(lambda url: True):
                self.click(self.sign_in_button)
            self._wait_for_step(self.home_header, step="password")

    def switch_account(self) -> None:
        """From the password step back to an empty username step."""
        self.log.info("Switching account")
        self.click(self.switch_account_link)
        self.wait_until_visible(self.username_input)

    # --- state ------------------------------------------------------------

    def error_text(self) -> str | None:
        """The inline error eBay shows under the field, or None."""
        if not self.error_message.is_visible():
            return None
        return self.error_message.inner_text().strip()

    def is_open(self) -> bool:
        """Still on the sign-in host, i.e. not sent on to eBay after a sign-in."""
        return Locators.HOST_PART in self.page.url

    def is_on_username_step(self) -> bool:
        return self.username_input.is_visible() and not self.password_input.is_visible()

    def is_on_password_step(self) -> bool:
        return self.password_input.is_visible()

    def account_shown(self) -> str:
        """The username the password step is asking for, as eBay echoes it."""
        return self.text_of(self.user_info)

    def is_sign_in_enabled(self) -> bool:
        return self.sign_in_button.is_enabled()

    def password_field_type(self) -> str | None:
        return self.password_input.get_attribute("type")

    def username_value(self) -> str:
        return self.username_input.input_value()

    def password_value(self) -> str:
        return self.password_input.input_value()

    # --- helpers ----------------------------------------------------------

    def _wait_for_step(self, expected: Locator, step: str) -> None:
        """Wait for the next step or an inline error; a captcha or an unknown page raises."""
        try:
            # Visible ones only: eBay keeps the hidden #pass in the DOM on the username
            # step, and plain `.first` would wait on it instead of the error after it.
            expected.or_(self.error_message).filter(visible=True).first.wait_for(state="visible")
        except PlaywrightTimeoutError:
            self.ensure_not_blocked()
            raise LoginError(
                f"Sign-in stopped after the {step} step at {self.page.url} "
                f"(likely an extra check such as 2FA or a passkey prompt). Use guest mode: {EnvVar.GUEST}=true."
            ) from None

    def _raise_on_error(self, step: str) -> None:
        if (error := self.error_text()) is not None:
            raise LoginError(f"eBay rejected the {step}: {error}")
