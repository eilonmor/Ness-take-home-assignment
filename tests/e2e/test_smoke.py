import re

import pytest
from playwright.sync_api import Page, expect

from core.config import Settings
from pages.home_page import HomePage


@pytest.mark.smoke
def test_ebay_home_page_opens(page: Page, settings: Settings) -> None:
    # HomePage.open() fails on eBay's bot-check pages; "Error Page | eBay" would match the title regex.
    HomePage(page, settings).open()
    expect(page).to_have_title(re.compile("ebay", re.IGNORECASE))
