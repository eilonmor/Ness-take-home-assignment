"""Browser fixtures driven by the active settings profile.

    pytest                  -> ENV from environment / .env, default "dev"
    pytest --env ci         -> config/ci.yaml
    ENV=ci pytest           -> same, via environment variable

One-off overrides on top of the profile:
    HEADLESS=false  SLOW_MO=250  BASE_URL=https://www.ebay.co.uk  BROWSER=firefox
(only Chromium is installed by default; for the others run
 ``python -m playwright install firefox webkit``)

On failure: a screenshot of every open page and the Playwright trace are
saved under reports/ and attached to the Allure report.

Data-driven: a test that takes a ``search_case`` argument runs once per row
of the profile's data file (``data.search_cases``, default
data/search_cases.yaml). Adding a row adds a test case.

Session: a test that takes ``user_session`` starts on the eBay home page as
a guest (default) or signed in (EBAY_GUEST=false + credentials in .env).
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from playwright.sync_api import Browser, BrowserContext, Page, Playwright, expect, sync_playwright

from core.config import Settings, load_settings
from core.constants import ArtifactFiles, AttachmentName, PytestOption, TraceMode
from core.data_loader import load_search_cases
from core.logger import configure_logging, get_logger
from services.auth_service import AuthService, UserSession
from utils.attachments import attach_screenshot, attach_trace
from utils.files import safe_filename, timestamp

log = get_logger("conftest")

phase_reports_key = pytest.StashKey[dict[str, pytest.TestReport]]()
settings_key = pytest.StashKey[Settings]()


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(PytestOption.ENV, action="store", default=None, help="Settings profile from config/ (overrides $ENV).")


def _load_settings_once(config: pytest.Config) -> Settings:
    # Needed both at collection (data file path) and by the fixtures: load once per run.
    if settings_key not in config.stash:
        config.stash[settings_key] = load_settings(config.getoption(PytestOption.ENV))
    return config.stash[settings_key]


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    if PytestOption.SEARCH_CASE_ARG in metafunc.fixturenames:
        cases = load_search_cases(_load_settings_once(metafunc.config).data.search_cases)
        metafunc.parametrize(PytestOption.SEARCH_CASE_ARG, cases, ids=[case.id for case in cases])


@pytest.hookimpl(wrapper=True, tryfirst=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo[None]) -> Iterator[pytest.TestReport]:
    # Keep each phase's report on the item so fixtures can tell whether the test failed.
    report = yield
    item.stash.setdefault(phase_reports_key, {})[report.when] = report
    return report


def _test_failed(node: pytest.Item) -> bool:
    return any(report.failed for report in node.stash.get(phase_reports_key, {}).values())


@pytest.fixture(scope="session")
def settings(pytestconfig: pytest.Config) -> Settings:
    settings = _load_settings_once(pytestconfig)
    log_file = configure_logging(settings.artifacts.logs_dir, settings.log_level)
    expect.set_options(timeout=settings.timeouts.expect_ms)
    log.info(
        "Profile '%s': %s | %s headless=%s slow_mo=%sms | %s | log file %s",
        settings.env,
        settings.base_url,
        settings.browser.name,
        settings.browser.headless,
        settings.browser.slow_mo_ms,
        "guest" if settings.auth.guest else f"login as {settings.auth.username}",
        log_file,
    )
    return settings


@pytest.fixture(scope="session")
def playwright() -> Iterator[Playwright]:
    with sync_playwright() as playwright:
        yield playwright


@pytest.fixture(scope="session")
def browser(playwright: Playwright, settings: Settings) -> Iterator[Browser]:
    browser_type = getattr(playwright, settings.browser.name)
    browser = browser_type.launch(headless=settings.browser.headless, slow_mo=settings.browser.slow_mo_ms)
    yield browser
    browser.close()


@pytest.fixture
def context(browser: Browser, settings: Settings, request: pytest.FixtureRequest) -> Iterator[BrowserContext]:
    """Fresh, isolated context per test (own cookies/cart), with tracing."""
    context = browser.new_context(
        base_url=settings.base_url,
        locale=settings.locale,
        timezone_id=settings.timezone_id,
        viewport={"width": settings.browser.viewport_width, "height": settings.browser.viewport_height},
    )
    context.set_default_timeout(settings.timeouts.default_ms)
    context.set_default_navigation_timeout(settings.timeouts.navigation_ms)

    trace_mode = settings.artifacts.trace
    if trace_mode != TraceMode.OFF:
        context.tracing.start(title=request.node.nodeid, screenshots=True, snapshots=True, sources=True)

    yield context

    # Evidence is best effort: an error here must neither leak the context
    # nor replace the test's own failure in the report.
    try:
        failed = _test_failed(request.node)
        run_id = f"{timestamp()}_{safe_filename(request.node.name)}"
        if failed and settings.artifacts.screenshot_on_failure:
            _save_failure_screenshots(context, settings, run_id)
        _finish_tracing(context, settings, run_id, failed)
    except Exception as error:
        log.warning("Could not collect test evidence: %s", error)
    finally:
        context.close()


def _save_failure_screenshots(context: BrowserContext, settings: Settings, run_id: str) -> None:
    for index, page in enumerate(context.pages):
        file_name = ArtifactFiles.FAILURE_SCREENSHOT.format(run_id=run_id, index=index)
        path = settings.artifacts.screenshots_dir / f"{file_name}{ArtifactFiles.SCREENSHOT_SUFFIX}"
        try:
            page.screenshot(path=path, full_page=True)
            attach_screenshot(path, AttachmentName.FAILURE_SCREENSHOT.format(index=index))
        except Exception as error:  # page may already be closed/crashed
            log.warning("Could not capture failure screenshot of page %d: %s", index, error)
            continue
        log.info("Failure screenshot: %s", path)


def _finish_tracing(context: BrowserContext, settings: Settings, run_id: str, failed: bool) -> None:
    trace_mode = settings.artifacts.trace
    if trace_mode == TraceMode.ON or (trace_mode == TraceMode.RETAIN_ON_FAILURE and failed):
        trace_path = settings.artifacts.traces_dir / f"{run_id}{ArtifactFiles.TRACE_SUFFIX}"
        context.tracing.stop(path=trace_path)
        attach_trace(trace_path)
        log.info("Trace saved: %s (open with: playwright show-trace %s)", trace_path, trace_path)
    elif trace_mode != TraceMode.OFF:
        context.tracing.stop()


@pytest.fixture
def page(context: BrowserContext) -> Page:
    return context.new_page()


@pytest.fixture
def user_session(page: Page, settings: Settings) -> UserSession:
    """The page on eBay home, ready as guest or signed-in user (``auth`` settings)."""
    return AuthService(page, settings).start_session()
