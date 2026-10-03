import allure
import pytest
from playwright.sync_api import Page

from core.config import Settings
from core.data_loader import SearchCase
from services.auth_service import UserSession
from services.search_service import SearchService


@pytest.mark.e2e
@allure.feature("Search")
def test_search_items_by_name_under_price(
    page: Page, settings: Settings, user_session: UserSession, search_case: SearchCase
) -> None:
    """Spec 5.2, one run per row of data/search_cases.yaml: up to `limit` unique items, each priced <= max_price."""
    items = SearchService(page, settings).find_items_under_price(
        search_case.query, search_case.max_price, search_case.limit
    )

    # Fewer than `limit` (even 0) is valid for the function, but the data rows are
    # chosen to have matches: 0 here more likely means a broken locator.
    assert items, f"No items found for {search_case.query!r} <= {search_case.max_price:g}"
    assert len(items) <= search_case.limit
    urls = [item.url for item in items]
    assert len(set(urls)) == len(urls), f"Duplicate URLs: {urls}"
    for item in items:
        assert "/itm/" in item.url, item.url
        assert item.price is not None and item.price.high <= search_case.max_price, (
            f"{item.title!r} costs {item.price}, above {search_case.max_price:g}"
        )
