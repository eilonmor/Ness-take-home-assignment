"""Browser fixtures driven by the active settings profile.

    pytest                  -> ENV from environment / .env, default "dev"
    pytest --env ci         -> config/ci.yaml
    ENV=ci pytest           -> same, via environment variable

One-off overrides on top of the profile:
    HEADLESS=false  SLOW_MO=250  BASE_URL=https://www.ebay.co.uk  BROWSER=firefox
    TRACE=on  (keep the trace of a passing run too)
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
from typing import Any
from pathlib import Path

import pytest
from playwright.sync_api import Browser, BrowserContext, Page, Playwright, expect, sync_playwright

from core import stealth
from core.config import Settings, load_settings
from core.constants import TRACE_START_OPTIONS, ArtifactFiles, AttachmentName, HtmlReport, PytestOption, TraceMode
from core.data_loader import load_search_cases
from core.logger import configure_logging, get_logger
from services.auth_service import AuthService, UserSession
from utils.attachments import attach_screenshot, attach_trace, write_allure_environment
from utils.files import safe_filename, timestamp
from utils.html_report import screenshot_extra, trace_extra

log = get_logger("conftest")

phase_reports_key = pytest.StashKey[dict[str, pytest.TestReport]]()
settings_key = pytest.StashKey[Settings]()
html_extras_key = pytest.StashKey[list[Any]]()


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


def pytest_sessionfinish(session: pytest.Session) -> None:
    # allure-pytest stores --alluredir as `allure_report_dir`; absent when Allure is turned off.
    results_dir = session.config.getoption("allure_report_dir", default=None)
    if not results_dir:
        return
    # Report extra: a broken profile has already failed the run on its own.
    try:
        write_allure_environment(Path(results_dir), _environment(_load_settings_once(session.config)))
    except Exception as error:
        log.warning("Could not write the Allure environment: %s", error)


@pytest.hookimpl(optionalhook=True)
def pytest_html_report_title(report: Any) -> None:
    report.title = HtmlReport.TITLE


@pytest.hookimpl(optionalhook=True)
def pytest_metadata(metadata: dict[str, Any], config: pytest.Config) -> None:
    # The "Environment" table of the pytest-html report: the same settings as the Allure one.
    try:
        metadata.update(_environment(_load_settings_once(config)))
    except Exception as error:
        log.warning("Could not add the settings to the HTML report: %s", error)


def _environment(settings: Settings) -> dict[str, str]:
    return {
        "Profile": settings.env,
        "Base URL": settings.base_url,
        "Browser": settings.browser.name,
        "Headless": str(settings.browser.headless),
        "Stealth": str(settings.browser.stealth),
        "Channel": settings.browser.channel or "bundled",
        "Locale": settings.locale,
        "Currency": settings.currency,
        "Session": "guest" if settings.auth.guest else "signed in",
        "Cart total line": settings.cart.total_line,
        "Trace": settings.artifacts.trace,
        "Data file": settings.data.search_cases.name,
    }


@pytest.hookimpl(wrapper=True, tryfirst=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo[None]) -> Iterator[pytest.TestReport]:
    # Keep each phase's report on the item so fixtures can tell whether the test failed.
    report = yield
    item.stash.setdefault(phase_reports_key, {})[report.when] = report
    if report.when == "teardown":
        # Evidence is saved by the context fixture's teardown, which has run by now.
        report.extras = [*getattr(report, "extras", []), *item.stash.get(html_extras_key, [])]
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
    browser = browser_type.launch(**stealth.launch_options(settings))
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
        **stealth.context_options(browser, settings),
    )
    stealth.apply(context, settings)
    context.set_default_timeout(settings.timeouts.default_ms)
    context.set_default_navigation_timeout(settings.timeouts.navigation_ms)

    trace_mode = settings.artifacts.trace
    if trace_mode != TraceMode.OFF:
        context.tracing.start(title=request.node.nodeid, **TRACE_START_OPTIONS)

    yield context

    # Evidence is best effort: an error here must neither leak the context
    # nor replace the test's own failure in the report.
    try:
        failed = _test_failed(request.node)
        run_id = f"{timestamp()}_{safe_filename(request.node.name)}"
        html_extras = request.node.stash.setdefault(html_extras_key, [])
        if failed and settings.artifacts.screenshot_on_failure:
            for index, path in _save_failure_screenshots(context, settings, run_id):
                html_extras += screenshot_extra(path, AttachmentName.FAILURE_SCREENSHOT.format(index=index))
        trace_path = _finish_tracing(context, settings, run_id, failed)
        if trace_path is not None:
            html_report = request.config.getoption(HtmlReport.PATH_OPTION, default=None)
            html_extras += trace_extra(trace_path, Path(html_report) if html_report else None, AttachmentName.TRACE)
    except Exception as error:
        log.warning("Could not collect test evidence: %s", error)
    finally:
        context.close()


def _save_failure_screenshots(context: BrowserContext, settings: Settings, run_id: str) -> list[tuple[int, Path]]:
    saved = []
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
        saved.append((index, path))
    return saved


def _finish_tracing(context: BrowserContext, settings: Settings, run_id: str, failed: bool) -> Path | None:
    """Stop tracing; returns the saved trace file, if this run keeps one."""
    trace_mode = settings.artifacts.trace
    if trace_mode == TraceMode.ON or (trace_mode == TraceMode.RETAIN_ON_FAILURE and failed):
        trace_path = settings.artifacts.traces_dir / f"{run_id}{ArtifactFiles.TRACE_SUFFIX}"
        context.tracing.stop(path=trace_path)
        attach_trace(trace_path)
        log.info("Trace saved: %s (open with: playwright show-trace %s)", trace_path, trace_path)
        return trace_path
    if trace_mode != TraceMode.OFF:
        context.tracing.stop()
    return None


@pytest.fixture
def page(context: BrowserContext) -> Page:
    return context.new_page()


@pytest.fixture
def user_session(page: Page, settings: Settings) -> UserSession:
    """The page on eBay home, ready as guest or signed-in user (``auth`` settings)."""
    return AuthService(page, settings).start_session()
