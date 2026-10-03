"""Session setup: brings a fresh browser context to a ready state before a scenario."""

from __future__ import annotations

from dataclasses import dataclass

import allure
from playwright.sync_api import Page

from core.config import AuthSettings, Settings
from core.constants import ScreenshotName, TraceMode
from core.exceptions import LoginError
from core.logger import get_logger
from pages.home_page import HomePage
from pages.login_page import LoginPage
from utils.tracing import tracing_paused


@dataclass(frozen=True)
class UserSession:
    guest: bool
    username: str | None = None

    @property
    def label(self) -> str:
        return "guest" if self.guest else f"user {self.username}"


class AuthService:
    """Guest by default; real sign-in only when the profile / .env asks for it.

    eBay protects sign-in with captcha and bot checks, so guest mode is the
    supported path (a documented limitation). A guest can search and use the
    cart, which is all the scenario needs.
    """

    def __init__(self, page: Page, settings: Settings) -> None:
        self.page = page
        self.settings = settings
        self.log = get_logger(type(self).__name__)

    def start_session(self) -> UserSession:
        auth = self.settings.auth
        home = HomePage(self.page, self.settings)
        with allure.step("Open eBay home page"):
            home.open()

        session = self._continue_as_guest(home) if auth.guest else self._sign_in(home, auth)
        home.take_screenshot(ScreenshotName.SESSION_READY.format(label=session.label))
        self.log.info("Session ready as %s", session.label)
        return session

    def _continue_as_guest(self, home: HomePage) -> UserSession:
        with allure.step("Continue as guest (sign-in skipped: eBay shows captcha/bot checks)"):
            if home.header.is_signed_in():
                raise LoginError("Expected a guest session, but the header shows a signed-in user")
            return UserSession(guest=True)

    def _sign_in(self, home: HomePage, auth: AuthSettings) -> UserSession:
        # config.load_settings guarantees both credentials when guest is off.
        assert auth.username and auth.password
        with allure.step(f"Sign in as {auth.username}"):
            # Not traced: the trace would store the password in plain text.
            with tracing_paused(self.page.context, self.settings.artifacts.trace != TraceMode.OFF):
                home.header.click_sign_in()
                LoginPage(self.page, self.settings).sign_in(auth.username, auth.password)
            home.header.dismiss_ship_to_dialog()
            if not home.header.is_signed_in():
                raise LoginError(f"Sign-in finished, but the header still shows: {home.header.greeting()!r}")
            return UserSession(guest=False, username=auth.username)
