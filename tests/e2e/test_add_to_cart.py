import allure
import pytest
from playwright.sync_api import Page

from core.config import Settings
from core.data_loader import SearchCase
from services.auth_service import UserSession
from services.cart_service import CartService
from services.search_service import SearchService


@pytest.mark.e2e
@allure.feature("Cart")
def test_add_items_to_cart(page: Page, settings: Settings, user_session: UserSession, search_case: SearchCase) -> None:
    """Spec 5.3, one run per data row: every URL found by the search ends up in the cart."""
    urls = SearchService(page, settings).search_items_by_name_under_price(
        search_case.query, search_case.max_price, search_case.limit
    )
    assert urls, f"No items found for {search_case.query!r} <= {search_case.max_price:g}"
    search_url = page.url

    added = CartService(page, settings).add_items(urls)

    assert [item.url for item in added] == urls
    # One unit per item, so the header badge counts exactly the items added.
    assert added[-1].cart_count == len(urls), f"Cart shows {added[-1].cart_count} items, expected {len(urls)}"
    assert page.url == search_url, "Expected to be back on the search results tab"
    assert page.context.pages == [page], "Item tabs should be closed"
