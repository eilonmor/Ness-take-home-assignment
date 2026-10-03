import allure
import pytest
from playwright.sync_api import Page

from core.config import Settings
from core.constants import AllureFeature, AssertMessage, Expected
from core.data_loader import SearchCase
from services.auth_service import UserSession
from services.search_service import SearchService


@pytest.mark.e2e
@allure.feature(AllureFeature.SEARCH)
def test_search_items_by_name_under_price(
    page: Page, settings: Settings, user_session: UserSession, search_case: SearchCase
) -> None:
    """Spec 5.2, one run per row of data/search_cases.yaml: up to `limit` unique items, each priced <= max_price."""
    items = SearchService(page, settings).find_items_under_price(
        search_case.query, search_case.max_price, search_case.limit
    )

    # Fewer than `limit` (even 0) is valid for the function, but the data rows are
    # chosen to have matches: 0 here more likely means a broken locator.
    assert items, AssertMessage.NO_ITEMS_FOUND.format(query=search_case.query, max_price=search_case.max_price)
    assert len(items) <= search_case.limit
    urls = [item.url for item in items]
    assert len(set(urls)) == len(urls), AssertMessage.DUPLICATE_URLS.format(urls=urls)
    for item in items:
        assert Expected.ITEM_URL_PART in item.url, item.url
        assert item.price is not None and item.price.high <= search_case.max_price, (
            AssertMessage.PRICE_ABOVE_MAX.format(title=item.title, price=item.price, max_price=search_case.max_price)
        )


@pytest.mark.e2e
@allure.feature(AllureFeature.SEARCH)
def test_search_with_no_matches_returns_no_items(page: Page, settings: Settings, user_session: UserSession) -> None:
    """Spec 5.2 allows an empty result. eBay still fills a "0 results" page with fuzzy
    matches on parts of the query; none of them may be collected."""
    query = Expected.NO_MATCH_QUERY

    items = SearchService(page, settings).find_items_under_price(query, Expected.NO_MATCH_MAX_PRICE)

    assert items == [], AssertMessage.ITEMS_FOR_NO_MATCH.format(query=query, titles=[item.title for item in items])
