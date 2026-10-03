"""core.stealth, offline: launch options and the fingerprint seen by page scripts."""

from dataclasses import replace

import pytest
from playwright.sync_api import sync_playwright

from core import config, stealth
from core.config import Settings, load_settings


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.setattr(config, "load_dotenv", lambda *args, **kwargs: False)
    for name in ("STEALTH", "BROWSER_CHANNEL", "HEADLESS", "BROWSER"):
        monkeypatch.delenv(name, raising=False)
    return load_settings("ci")


def _with(settings: Settings, **browser: object) -> Settings:
    return replace(settings, browser=replace(settings.browser, **browser))


def test_off_keeps_plain_launch(settings: Settings) -> None:
    assert stealth.launch_options(settings) == {"headless": True, "slow_mo": 0}


def test_on_adds_flags_and_new_headless(settings: Settings) -> None:
    options = stealth.launch_options(_with(settings, stealth=True))

    assert "--disable-blink-features=AutomationControlled" in options["args"]
    assert options["ignore_default_args"] == ["--enable-automation"]
    assert options["channel"] == "chromium"


def test_explicit_channel_wins(settings: Settings) -> None:
    assert stealth.launch_options(_with(settings, stealth=True, channel="chrome"))["channel"] == "chrome"


def test_ignored_for_firefox(settings: Settings) -> None:
    assert "args" not in stealth.launch_options(_with(settings, stealth=True, name="firefox"))


def test_page_sees_no_automation_markers(settings: Settings) -> None:
    on = _with(settings, stealth=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(**stealth.launch_options(on))
        try:
            context = browser.new_context(**stealth.context_options(browser, on))
            stealth.apply(context, on)
            page = context.new_page()

            assert page.evaluate("navigator.webdriver") in (None, False)
            assert "HeadlessChrome" not in page.evaluate("navigator.userAgent")
        finally:
            browser.close()
