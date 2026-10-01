import pytest
from playwright.sync_api import Page

from components.header import Header
from core.config import Settings
from services.auth_service import UserSession


@pytest.mark.smoke
def test_session_is_ready(page: Page, settings: Settings, user_session: UserSession) -> None:
    """Guest by default (eBay sign-in has captcha); signed in when EBAY_GUEST=false."""
    header = Header(page, settings)

    assert user_session.guest is settings.auth.guest
    assert header.is_signed_in() is not user_session.guest, f"Header shows: {header.greeting()!r}"
