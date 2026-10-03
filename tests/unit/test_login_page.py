"""LoginPage step handling, checked offline against a stand-in for the two-step eBay sign-in form.

The markup keeps the ids and texts seen live on signin.ebay.com (2026-10). All
eBay URLs are answered by ``context.route``: no network. Like the live form,
Continue is handled in the page, and Sign in posts a form that answers with a
new page (the error page on /signin/s, or the home page).
"""

import uuid
import zipfile
from collections.abc import Iterator
from pathlib import Path
from urllib.parse import parse_qs

import pytest
from playwright.sync_api import Browser, BrowserContext, Page, Route, sync_playwright

from core.config import Settings, load_settings
from core.constants import LoginErrorText
from core.exceptions import LoginError
from pages.login_page import LoginPage

SIGN_IN_URL = "https://signin.ebay.com/signin"
HOME_URL = "https://www.ebay.com/"
USERNAME = "qa-user@example.com"
UNKNOWN = "nobody@example.com"
PASSKEY_USER = "passkey-user@example.com"  # eBay offers this one a passkey after the password
PASSKEY_URL = "https://accounts.ebay.com/acctsec/authn-register?srt=x&ru=https%3A%2F%2Fwww.ebay.com%2F"
PASSWORD = f"Right-{uuid.uuid4().hex}"  # generated: traces pack this source file too

SIGN_IN_PAGE = """
<h1 id="welcome-msg">{heading}</h1>
<span id="switch-account-link"{user_hidden}><a id="switch-account-anchor">Switch account</a></span>
<span id="user-info">{user}</span>
<div id="username-step"{username_hidden}>
  <input id="userid"><button id="signin-continue-btn" type="button">Continue</button>
</div>
<form id="password-step" method="post" action="/signin/s"{password_hidden}>
  <input type="hidden" name="userid" value="{user}">
  <input id="pass" name="pass" type="password"><button id="sgnBt" disabled>Sign in</button>
</form>
<p id="signin-error-msg"{error_hidden}>{error}</p>
<script>
  const error = document.querySelector('#signin-error-msg');
  const showPasswordStep = (user) => {{
    document.querySelector('#welcome-msg').textContent = 'Welcome back!';
    document.querySelector('#user-info').textContent = user;
    document.querySelector('[name=userid]').value = user;
    document.querySelector('#username-step').hidden = true;
    document.querySelector('#password-step').hidden = false;
    document.querySelector('#switch-account-link').hidden = false;
  }};
  document.querySelector('#signin-continue-btn').onclick = () => {{
    const user = document.querySelector('#userid').value.trim();
    error.hidden = true;
    if (!user) {{ error.textContent = "Oops, that's not a match."; error.hidden = false; return; }}
    if (user.toLowerCase() === '{unknown}') {{
      error.textContent = "We couldn't find this eBay account. Try again or create an account.";
      error.hidden = false;
      return;
    }}
    showPasswordStep(user);
  }};
  document.querySelector('#pass').oninput = (event) => {{
    document.querySelector('#sgnBt').disabled = !event.target.value;
  }};
  document.querySelector('#switch-account-link').onclick = () => {{
    document.querySelector('#welcome-msg').textContent = 'Sign in to your account';
    document.querySelector('#userid').value = '';
    document.querySelector('#username-step').hidden = false;
    document.querySelector('#password-step').hidden = true;
    document.querySelector('#switch-account-link').hidden = true;
  }};
</script>
"""

HOME_PAGE = '<div id="gh"><div class="gh-identity">Hi Qa!</div></div>'
PASSKEY_PAGE = f"""
<h1>Simplify your sign-in</h1>
<button id="add-passkey-btn">Continue</button>
<a id="passkeys-cancel-btn" href="{HOME_URL}">Skip for now</a>
"""


def sign_in_page(user: str = "", error: str = "") -> str:
    on_password_step = bool(user)
    return SIGN_IN_PAGE.format(
        heading="Welcome back!" if on_password_step else "Sign in to your account",
        user=user,
        unknown=UNKNOWN,
        error=error,
        user_hidden="" if on_password_step else " hidden",
        username_hidden=" hidden" if on_password_step else "",
        password_hidden="" if on_password_step else " hidden",
        error_hidden="" if error else " hidden",
    )


def fake_ebay(route: Route) -> None:
    request = route.request
    if request.url.startswith(SIGN_IN_URL + "/s"):
        form = parse_qs(request.post_data or "")
        if form.get("pass") == [PASSWORD]:
            next_url = PASSKEY_URL if form.get("userid") == [PASSKEY_USER] else HOME_URL
            # A JS redirect, not a 302: a routed request's redirect would go to the real network.
            route.fulfill(content_type="text/html", body=f"<script>location.replace('{next_url}')</script>")
            return
        user = form.get("userid", [""])[0]
        route.fulfill(content_type="text/html", body=sign_in_page(user, "This password is incorrect. Try again or reset password."))
    elif request.url.startswith(PASSKEY_URL.split("?")[0]):
        route.fulfill(content_type="text/html", body=PASSKEY_PAGE)
    elif request.url.startswith(SIGN_IN_URL):
        route.fulfill(content_type="text/html", body=sign_in_page())
    else:
        route.fulfill(content_type="text/html", body=HOME_PAGE)


@pytest.fixture(scope="module")
def settings() -> Settings:
    return load_settings("ci")


@pytest.fixture(scope="module")
def browser() -> Iterator[Browser]:
    # Local HTML only: no eBay traffic, so headless is fine here.
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        yield browser
        browser.close()


@pytest.fixture
def context(browser: Browser, settings: Settings) -> Iterator[BrowserContext]:
    context = browser.new_context()
    context.set_default_timeout(3000)
    context.route("https://*.ebay.com/**", fake_ebay)
    # Active like in a real run (the profile traces), so submit_password's pause is exercised.
    context.tracing.start(snapshots=True, screenshots=True, sources=True)
    yield context
    context.close()


@pytest.fixture
def login(context: BrowserContext, settings: Settings) -> LoginPage:
    page: Page = context.new_page()
    page.goto(SIGN_IN_URL)
    return LoginPage(page, settings).wait_until_loaded()


@pytest.mark.parametrize(
    ("username", "expected"),
    [("", LoginErrorText.EMPTY_USERNAME), (UNKNOWN, LoginErrorText.UNKNOWN_ACCOUNT)],
    ids=["empty", "unknown"],
)
def test_rejected_username_stops_on_the_username_step_with_the_error(login: LoginPage, username: str, expected: str) -> None:
    login.submit_username(username)

    assert expected in login.error_text()
    assert login.is_on_username_step()
    assert not login.is_on_password_step()


def test_known_username_reaches_the_password_step(login: LoginPage) -> None:
    login.submit_username(USERNAME)

    assert login.error_text() is None
    assert login.is_on_password_step()
    assert login.account_shown() == USERNAME
    assert login.password_field_type() == "password"
    assert not login.is_sign_in_enabled()


def test_wrong_password_returns_the_error_page_with_an_empty_field(login: LoginPage) -> None:
    login.submit_username(USERNAME)
    login.submit_password("wrong")

    assert LoginErrorText.WRONG_PASSWORD in login.error_text()
    assert login.is_open()
    assert login.is_on_password_step()
    assert login.password_value() == ""


def test_retry_after_a_wrong_password_waits_for_the_new_answer(login: LoginPage) -> None:
    """The old error is still on screen when Sign in is clicked again; it must not count as the answer."""
    login.submit_username(USERNAME)
    login.submit_password("wrong")
    login.submit_password(PASSWORD)

    assert login.page.url == HOME_URL
    assert not login.is_open()


def test_switch_account_goes_back_to_an_empty_username(login: LoginPage) -> None:
    login.submit_username(USERNAME)
    login.switch_account()

    assert login.is_on_username_step()
    assert login.username_value() == ""


@pytest.mark.parametrize(
    ("username", "password", "rejected_step"),
    [(UNKNOWN, PASSWORD, "username"), (USERNAME, "wrong", "password")],
    ids=["username", "password"],
)
def test_sign_in_raises_login_error_naming_the_rejected_step(
    login: LoginPage, username: str, password: str, rejected_step: str
) -> None:
    with pytest.raises(LoginError, match=f"rejected the {rejected_step}"):
        login.sign_in(username, password)


def test_sign_in_lands_on_the_home_page(login: LoginPage) -> None:
    login.sign_in(USERNAME, PASSWORD)

    assert login.page.url == HOME_URL


def test_passkey_offer_after_the_password_is_skipped(login: LoginPage) -> None:
    """"Simplify your sign-in" (seen live, 2026-10): Skip for now, and the sign-in ends on the home page."""
    login.sign_in(PASSKEY_USER, PASSWORD)

    assert login.page.url == HOME_URL


def test_sign_in_answered_inside_the_page_raises_login_error(login: LoginPage) -> None:
    """No new page after Sign in (e.g. an in-page check): LoginError naming the step, not a bare Playwright timeout."""
    login.submit_username(USERNAME)
    login.page.evaluate("() => { document.querySelector('#password-step').onsubmit = (event) => event.preventDefault(); }")

    with pytest.raises(LoginError, match="stopped after the password step"):
        login.submit_password("anything")


def test_the_typed_password_stays_out_of_the_trace(login: LoginPage, context: BrowserContext, tmp_path: Path) -> None:
    login.sign_in(USERNAME, PASSWORD)
    context.tracing.stop(path=tmp_path / "trace.zip")

    with zipfile.ZipFile(tmp_path / "trace.zip") as trace:
        assert not any(PASSWORD.encode() in trace.read(name) for name in trace.namelist())
