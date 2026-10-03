import allure
import pytest
from playwright.sync_api import Page

from core.config import Settings
from core.constants import AllureFeature, AssertMessage
from core.data_loader import SearchCase
from pages.cart_page import CartPage
from services.auth_service import UserSession
from services.cart_service import CartService
from services.search_service import SearchService


@pytest.mark.e2e
@allure.feature(AllureFeature.CART)
def test_cart_total_not_exceeds_budget(
    page: Page, settings: Settings, user_session: UserSession, search_case: SearchCase
) -> None:
    """Spec 5.4 after 5.2 and 5.3, one run per data row: cart total <= budget_per_item * items added."""
    urls = SearchService(page, settings).search_items_by_name_under_price(
        search_case.query, search_case.max_price, search_case.limit
    )
    assert urls, AssertMessage.NO_ITEMS_FOUND.format(query=search_case.query, max_price=search_case.max_price)
    cart = CartService(page, settings)
    cart.add_items_to_cart(urls)

    cart.assert_cart_total_not_exceeds(search_case.budget, len(urls))

    # Left on the cart page. Fresh context per test, so it holds exactly the items added above.
    lines = CartPage(page, settings).lines()
    assert len(lines) == len(urls), AssertMessage.CART_LINES.format(actual=len(lines), expected=len(urls))
