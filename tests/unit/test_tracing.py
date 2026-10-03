"""tracing_paused keeps typed secrets out of the trace zip.

Runs headless Chromium on inline HTML (no network). The secret is generated
at runtime: traces also pack this source file, so a literal would match.
"""

import uuid
import zipfile
from collections.abc import Iterator
from pathlib import Path

import pytest
from playwright.sync_api import Browser, sync_playwright

from utils.tracing import tracing_paused

LOGIN_FORM = '<input id="user"><input id="pass" type="password">'
POST_FORM = '<form method="post" action="/s"><input id="pass" name="pass" type="password"><button>Sign in</button></form>'


@pytest.fixture(scope="module")
def browser() -> Iterator[Browser]:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        yield browser
        browser.close()


@pytest.fixture
def secret() -> str:
    return f"pw-{uuid.uuid4().hex}"


def _trace_contains(path: Path, text: str) -> bool:
    with zipfile.ZipFile(path) as trace:
        return any(text.encode() in trace.read(name) for name in trace.namelist())


def _record(browser: Browser, path: Path, secret: str, paused: bool) -> None:
    context = browser.new_context()
    context.tracing.start(screenshots=True, snapshots=True, sources=True)
    page = context.new_page()
    page.set_content(LOGIN_FORM)
    with tracing_paused(context, tracing_active=paused):
        page.fill("#pass", secret)
        page.set_content("<p>signed in</p>")  # the password field is gone afterwards, as after a real sign-in
    page.click("p")
    context.tracing.stop(path=path)
    context.close()


def test_unpaused_trace_records_the_password(browser: Browser, secret: str, tmp_path: Path) -> None:
    """Control: proves the check below would catch a leak."""
    _record(browser, tmp_path / "trace.zip", secret, paused=False)

    assert _trace_contains(tmp_path / "trace.zip", secret)


def test_paused_trace_omits_the_password_and_keeps_recording(browser: Browser, secret: str, tmp_path: Path) -> None:
    _record(browser, tmp_path / "trace.zip", secret, paused=True)

    assert not _trace_contains(tmp_path / "trace.zip", secret)
    assert _trace_contains(tmp_path / "trace.zip", "signed in")  # recording resumed after the block


def test_paused_trace_omits_a_password_sent_in_a_form_post(browser: Browser, secret: str, tmp_path: Path) -> None:
    """The network log keeps request bodies, and eBay posts the password as a form field."""
    context = browser.new_context()
    context.route(
        "https://signin.test/**",
        lambda route: route.fulfill(
            content_type="text/html",
            body=POST_FORM if route.request.method == "GET" else "<p>signed in</p>",
        ),
    )
    context.tracing.start(screenshots=True, snapshots=True, sources=True)
    page = context.new_page()
    page.goto("https://signin.test/")
    with tracing_paused(context, tracing_active=True):
        page.fill("#pass", secret)
        with page.expect_navigation():
            page.click("button")
    page.click("p")
    context.tracing.stop(path=tmp_path / "trace.zip")
    context.close()

    assert not _trace_contains(tmp_path / "trace.zip", secret)
    assert _trace_contains(tmp_path / "trace.zip", "signed in")


def test_tracing_resumes_when_the_block_fails(browser: Browser, tmp_path: Path) -> None:
    context = browser.new_context()
    context.tracing.start(snapshots=True)
    with pytest.raises(RuntimeError), tracing_paused(context, tracing_active=True):
        raise RuntimeError("sign-in failed")

    context.tracing.stop(path=tmp_path / "trace.zip")  # what the fixture teardown does
    context.close()

    assert (tmp_path / "trace.zip").is_file()


def test_inactive_tracing_is_left_alone(browser: Browser) -> None:
    context = browser.new_context()  # no tracing.start(): stop() would raise
    with tracing_paused(context, tracing_active=False):
        pass
    context.close()
