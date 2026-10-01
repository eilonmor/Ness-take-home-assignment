import re
from urllib.parse import quote_plus

import pytest
from playwright.sync_api import Page, expect

from core.data_loader import SearchCase


@pytest.mark.smoke
def test_search_results_page_opens(page: Page, search_case: SearchCase) -> None:
    """One run per row of data/search_cases.yaml: the results page loads for the query."""
    # Headless + cold deep link to /sch gets eBay's "Error Page" (bot check);
    # landing on the home page first sets the session cookies, like a real user.
    page.goto("/")
    page.goto(f"/sch/i.html?_nkw={quote_plus(search_case.query)}")
    expect(page).to_have_title(re.compile(re.escape(search_case.query), re.IGNORECASE))
