"""BasePage.expect_navigation, offline: pages are served by a route, not by eBay."""

from collections.abc import Iterator

import pytest
from playwright.sync_api import Page, Route, sync_playwright

from core.base_page import BasePage
from core.config import Settings, load_settings
from core.exceptions import BotChallengeError

SITE = "https://shop.test"


def results_page(next_url: str) -> str:
    # Navigates a moment after the click, like eBay's search box and price filter.
    return f"""<title>Results | eBay</title>
    <button onclick="setTimeout(() => location.href = '{next_url}', 300)">go</button>"""


def serve(route: Route) -> None:
    url = route.request.url
    if "/splashui/challenge" in url:
        body = "<title>Pardon Our Interruption...</title>"
    elif "_nkw=first" in url:
        body = results_page(f"{SITE}/sch/i.html?_nkw=second")
    elif "_nkw=blocked" in url:
        body = results_page(f"{SITE}/splashui/challenge?ru=x")
    else:
        body = "<title>Second results | eBay</title>"
    route.fulfill(status=200, content_type="text/html", body=body)


@pytest.fixture(scope="module")
def settings() -> Settings:
    return load_settings("ci")


@pytest.fixture
def page() -> Iterator[Page]:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context()
        context.route(f"{SITE}/**", serve)
        yield context.new_page()
        browser.close()


def test_waits_for_the_new_page_even_if_the_current_url_already_matches(page: Page, settings: Settings) -> None:
    page.goto(f"{SITE}/sch/i.html?_nkw=first")
    seen_types: set[type] = set()

    def arrived(url: str) -> bool:
        seen_types.add(type(url))
        return "/sch/" in url

    with BasePage(page, settings).expect_navigation(arrived):
        page.click("button")

    assert page.url.endswith("_nkw=second")
    assert page.title() == "Second results | eBay"
    assert seen_types == {str}  # Python Playwright passes the URL as a string


def test_bot_check_redirect_ends_the_wait_with_a_clear_error(page: Page, settings: Settings) -> None:
    page.goto(f"{SITE}/sch/i.html?_nkw=blocked")

    with pytest.raises(BotChallengeError, match="Pardon Our Interruption"):
        with BasePage(page, settings).expect_navigation(lambda url: "/sch/" in url):
            page.click("button")
