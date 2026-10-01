import pytest

from core.base_page import bot_challenge_reason


@pytest.mark.parametrize(
    ("title", "url"),
    [
        ("Pardon Our Interruption...", "https://www.ebay.com/sch/i.html?_nkw=shoes"),
        ("Error Page | eBay", "https://www.ebay.com/"),
        ("Security Measure | eBay", "https://www.ebay.com/splashui/captcha?ap=1"),
        ("", "https://www.ebay.com/splashui/challenge?ru=x"),
    ],
)
def test_bot_check_pages_are_detected(title: str, url: str) -> None:
    assert bot_challenge_reason(title, url) is not None


@pytest.mark.parametrize(
    ("title", "url"),
    [
        ("Electronics, Cars, Fashion, Collectibles & More | eBay", "https://www.ebay.com/"),
        ("Sign in or Register | eBay", "https://signin.ebay.com/ws/eBayISAPI.dll?SignIn"),
        # Only the title prefix counts: an item may mention these words.
        ("Error Page T-Shirt | eBay", "https://www.ebay.com/itm/123"),
    ],
)
def test_normal_pages_are_not_flagged(title: str, url: str) -> None:
    assert bot_challenge_reason(title, url) is None
