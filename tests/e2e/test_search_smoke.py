from urllib.parse import quote_plus

import pytest
from playwright.sync_api import Page

from core.constants import Endpoints, QueryParam
from core.data_loader import SearchCase
from services.auth_service import UserSession
from utils.text import fold


@pytest.mark.smoke
def test_search_results_page_opens(page: Page, user_session: UserSession, search_case: SearchCase) -> None:
    """One run per row of data/search_cases.yaml: the results page loads for the query."""
    # user_session lands on the home page first: a cold deep link to /sch gets
    # eBay's "Error Page" (bot check) in headless mode.
    page.goto(f"{Endpoints.SEARCH}?{QueryParam.KEYWORDS}={quote_plus(search_case.query)}")
    # Accent-insensitive: eBay titles a "pokémon cards" search "Pokemon Cards for sale | eBay".
    assert fold(search_case.query) in fold(page.title()), page.title()
