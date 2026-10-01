"""Base class for every page object and component."""

from __future__ import annotations

from pathlib import Path
from typing import Self

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Locator, Page
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from core.config import Settings
from core.logger import get_logger
from utils.attachments import attach_screenshot
from utils.files import safe_filename, timestamp


class BasePage:
    """Navigation, waits, safe actions and screenshots shared by all pages.

    Subclasses set ``path`` (relative to ``Settings.base_url``) and expose
    locators + business-level methods; tests never touch raw selectors.
    """

    path: str = "/"

    def __init__(self, page: Page, settings: Settings) -> None:
        self.page = page
        self.settings = settings
        self.log = get_logger(type(self).__name__)

    # --- navigation -------------------------------------------------------

    def open(self) -> Self:
        self.log.info("Opening %s", self.path)
        self.page.goto(self.path, wait_until="domcontentloaded")
        return self

    def go_back(self) -> None:
        self.log.debug("Navigating back from %s", self.page.url)
        self.page.go_back(wait_until="domcontentloaded")

    @property
    def url(self) -> str:
        return self.page.url

    # --- waits ------------------------------------------------------------

    def wait_until_visible(self, locator: Locator, timeout_ms: float | None = None) -> Locator:
        locator.wait_for(state="visible", timeout=timeout_ms)
        return locator

    def is_visible(self, locator: Locator, timeout_ms: float = 2000) -> bool:
        """Non-throwing visibility check, for optional elements (popups, filters)."""
        try:
            locator.wait_for(state="visible", timeout=timeout_ms)
        except PlaywrightTimeoutError:
            return False
        return True

    # --- actions ----------------------------------------------------------

    def click(self, locator: Locator, retries: int = 1) -> None:
        """Click once visible; retry if e.g. an overlay intercepted the first attempt."""
        for attempt in range(retries + 1):
            try:
                self.wait_until_visible(locator)
                locator.scroll_into_view_if_needed()
                locator.click()
                return
            except PlaywrightError as error:
                if attempt == retries:
                    raise
                self.log.warning("Click attempt %d failed, retrying: %s", attempt + 1, _first_line(error))

    def fill(self, locator: Locator, value: str) -> None:
        self.wait_until_visible(locator).fill(value)

    def text_of(self, locator: Locator) -> str:
        return self.wait_until_visible(locator).inner_text().strip()

    # --- evidence ---------------------------------------------------------

    def take_screenshot(self, name: str, full_page: bool = False) -> Path:
        """Save a screenshot under reports/screenshots and attach it to Allure."""
        path = self.settings.artifacts.screenshots_dir / f"{timestamp()}_{safe_filename(name)}.png"
        self.page.screenshot(path=path, full_page=full_page)
        attach_screenshot(path, name)
        self.log.info("Screenshot saved: %s", path)
        return path


def _first_line(error: Exception) -> str:
    return str(error).splitlines()[0] if str(error) else type(error).__name__
