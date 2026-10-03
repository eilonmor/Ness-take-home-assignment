import uuid

import allure
import pytest
from playwright.sync_api import Page

from components.header import Header
from core.config import AuthSettings, Settings
from core.constants import AssertMessage, EnvVar, LoginErrorText, ScreenshotName
from pages.login_page import LoginPage
from services.auth_service import AuthService, UserSession

# eBay counts failed attempts per account; the suite makes three per run
# (wrong password, wrong case, retry). Keep it that way so the test account
# is not locked or sent to a captcha.
UNKNOWN_ACCOUNT = "no-such-user-ness-qa@example.com"


@pytest.fixture
def account(settings: Settings) -> AuthSettings:
    """The real test account from .env; the test is skipped without one."""
    if not (settings.auth.username and settings.auth.password):
        pytest.skip(f"Needs {EnvVar.USERNAME} and {EnvVar.PASSWORD} in the environment or .env")
    return settings.auth


@pytest.fixture
def login_page(page: Page, settings: Settings) -> LoginPage:
    """The sign-in form, opened from the home page header like a user would."""
    return AuthService(page, settings).open_sign_in_page()


@pytest.fixture
def account_login_page(account: AuthSettings, page: Page, settings: Settings) -> LoginPage:
    """Like ``login_page``, for tests that need the account: without credentials
    they are skipped before anything is opened on eBay."""
    return AuthService(page, settings).open_sign_in_page()


def _wrong_password() -> str:
    return f"Wrong-{uuid.uuid4().hex[:10]}"


def _assert_rejected(login_page: LoginPage, expected: str, step: str) -> None:
    error = login_page.error_text()
    login_page.take_screenshot(ScreenshotName.SIGN_IN_REJECTED.format(step=step))
    assert error is not None and expected.lower() in error.lower(), AssertMessage.LOGIN_ERROR.format(
        expected=expected, actual=error
    )
    assert login_page.is_open()


@pytest.mark.smoke
def test_session_is_ready(page: Page, settings: Settings, user_session: UserSession) -> None:
    """Guest by default (eBay sign-in has captcha); signed in when EBAY_GUEST=false."""
    header = Header(page, settings)

    assert user_session.guest is settings.auth.guest
    assert header.is_signed_in() is not user_session.guest, AssertMessage.HEADER_SHOWS.format(
        greeting=header.greeting()
    )


@pytest.mark.login
@pytest.mark.parametrize(
    ("username", "expected_error"),
    [("", LoginErrorText.EMPTY_USERNAME), (UNKNOWN_ACCOUNT, LoginErrorText.UNKNOWN_ACCOUNT)],
    ids=["empty-username", "unknown-account"],
)
def test_invalid_username_is_rejected(login_page: LoginPage, username: str, expected_error: str) -> None:
    with allure.step(f"Continue with username {username!r}"):
        login_page.submit_username(username)

    _assert_rejected(login_page, expected_error, step="username")
    assert login_page.is_on_username_step(), AssertMessage.LOGIN_STEP.format(expected="username")


@pytest.mark.login
def test_password_step_for_a_known_account(account: AuthSettings, account_login_page: LoginPage) -> None:
    """Before any password is typed: the right account, a masked field, Sign in disabled."""
    account_login_page.submit_username(account.username)

    assert account_login_page.error_text() is None
    assert account_login_page.is_on_password_step(), AssertMessage.LOGIN_STEP.format(expected="password")
    assert account_login_page.account_shown().lower() == account.username.lower()
    assert account_login_page.password_field_type() == "password", AssertMessage.PASSWORD_NOT_MASKED.format(
        actual=account_login_page.password_field_type()
    )
    assert not account_login_page.is_sign_in_enabled()


@pytest.mark.login
def test_username_is_trimmed_and_case_insensitive(account: AuthSettings, account_login_page: LoginPage) -> None:
    account_login_page.submit_username(f"  {account.username.upper()}  ")

    assert account_login_page.error_text() is None
    assert account_login_page.is_on_password_step(), AssertMessage.LOGIN_STEP.format(expected="password")


@pytest.mark.login
def test_wrong_password_is_rejected(account: AuthSettings, account_login_page: LoginPage) -> None:
    account_login_page.submit_username(account.username)
    with allure.step("Sign in with a wrong password"):
        account_login_page.submit_password(_wrong_password())

    _assert_rejected(account_login_page, LoginErrorText.WRONG_PASSWORD, step="password")
    assert account_login_page.is_on_password_step(), AssertMessage.LOGIN_STEP.format(expected="password")
    assert account_login_page.password_value() == "", AssertMessage.PASSWORD_NOT_CLEARED


@pytest.mark.login
def test_password_is_case_sensitive(account: AuthSettings, account_login_page: LoginPage) -> None:
    wrong_case = account.password.swapcase()
    if wrong_case == account.password:
        pytest.skip("The test account's password has no letters to swap the case of")

    account_login_page.submit_username(account.username)
    with allure.step("Sign in with the right password in the wrong case"):
        account_login_page.submit_password(wrong_case)

    _assert_rejected(account_login_page, LoginErrorText.WRONG_PASSWORD, step="password")


@pytest.mark.login
def test_switch_account_returns_to_username_step(account: AuthSettings, account_login_page: LoginPage) -> None:
    account_login_page.submit_username(account.username)
    account_login_page.switch_account()

    assert account_login_page.is_on_username_step(), AssertMessage.LOGIN_STEP.format(expected="username")
    assert account_login_page.username_value() == ""


@pytest.mark.login
def test_sign_in_succeeds_after_a_wrong_password(
    account: AuthSettings, page: Page, settings: Settings, account_login_page: LoginPage
) -> None:
    """A rejected password does not block the account: the right one still signs in."""
    account_login_page.submit_username(account.username)
    with allure.step("Sign in with a wrong password"):
        account_login_page.submit_password(_wrong_password())
    _assert_rejected(account_login_page, LoginErrorText.WRONG_PASSWORD, step="password")

    with allure.step(f"Sign in again as {account.username} with the right password"):
        account_login_page.submit_password(account.password)

    header = Header(page, settings)
    header.dismiss_ship_to_dialog()
    assert account_login_page.error_text() is None
    assert header.is_signed_in(), AssertMessage.HEADER_SHOWS.format(greeting=header.greeting())
