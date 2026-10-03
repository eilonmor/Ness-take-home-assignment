"""Browser hardening against automation fingerprinting (``browser.stealth``).

Experimental, Chromium only, off by default. It removes what marks the
browser as automated; it does not solve or bypass a CAPTCHA, and a bot
check that still appears is reported by ``BasePage.ensure_not_blocked()``
as before.

    launch_options(settings)          -> kwargs for ``browser_type.launch()``
    context_options(browser, settings) -> extra kwargs for ``browser.new_context()``
    apply(context, settings)          -> init scripts on a new context
"""

from __future__ import annotations

from functools import cache
from typing import Any

from playwright.sync_api import Browser, BrowserContext

from core.config import Settings
from core.constants import BrowserName, Stealth
from core.logger import get_logger

log = get_logger("stealth")

# New headless = the full Chromium build, not the separate headless shell,
# whose fingerprint (plugins, codecs, GPU) differs from a real browser.
_NEW_HEADLESS_CHANNEL = "chromium"


def enabled(settings: Settings) -> bool:
    if settings.browser.stealth and settings.browser.name != BrowserName.CHROMIUM:
        log.warning("browser.stealth is Chromium only; ignored for %s", settings.browser.name)
        return False
    return settings.browser.stealth


def launch_options(settings: Settings) -> dict[str, Any]:
    browser = settings.browser
    options: dict[str, Any] = {"headless": browser.headless, "slow_mo": browser.slow_mo_ms}
    channel = browser.channel
    if enabled(settings):
        options["args"] = list(Stealth.LAUNCH_ARGS)
        options["ignore_default_args"] = list(Stealth.IGNORE_DEFAULT_ARGS)
        if channel is None and browser.headless:
            channel = _NEW_HEADLESS_CHANNEL
    if channel:
        options["channel"] = channel
    return options


def context_options(browser: Browser, settings: Settings) -> dict[str, Any]:
    if not enabled(settings):
        return {}
    width, height = settings.browser.viewport_width, settings.browser.viewport_height
    # window.screen defaults to the viewport only in some modes; keep them consistent.
    options: dict[str, Any] = {"screen": {"width": width, "height": height}}
    user_agent = _real_user_agent(browser)
    if Stealth.HEADLESS_UA_TOKEN in user_agent:
        # Same browser and version, minus the headless marker: no hard-coded UA to go stale.
        options["user_agent"] = user_agent.replace(Stealth.HEADLESS_UA_TOKEN, Stealth.HEADED_UA_TOKEN)
    log.info("Stealth on: %s, UA %s", browser.version, options.get("user_agent", "unchanged"))
    return options


def apply(context: BrowserContext, settings: Settings) -> None:
    if enabled(settings):
        context.add_init_script(Stealth.INIT_SCRIPT)


@cache  # once per (session-scoped) browser, not per test context
def _real_user_agent(browser: Browser) -> str:
    probe = browser.new_page()
    try:
        return probe.evaluate("navigator.userAgent")
    finally:
        probe.context.close()
