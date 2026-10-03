import re
from urllib.parse import quote_plus

import pytest
from playwright.sync_api import Page, expect

from core.constants import Endpoints, QueryParam
from core.data_loader import SearchCase
from services.auth_service import UserSession


@pytest.mark.smoke
def test_search_results_page_opens(page: Page, user_session: UserSession, search_case: SearchCase) -> None:
    """One run per row of data/search_cases.yaml: the results page loads for the query."""
    # user_session lands on the home page first: a cold deep link to /sch gets
    # eBay's "Error Page" (bot check) in headless mode.
    page.goto(f"{Endpoints.SEARCH}?{QueryParam.KEYWORDS}={quote_plus(search_case.query)}")
    expect(page).to_have_title(re.compile(re.escape(search_case.query), re.IGNORECASE))
