import re

import pytest
from playwright.sync_api import Page, expect


@pytest.mark.smoke
def test_ebay_home_page_opens(page: Page) -> None:
    page.goto("https://www.ebay.com/")
    expect(page).to_have_title(re.compile("ebay", re.IGNORECASE))
