import allure
import pytest
from playwright.sync_api import Page

from core.config import Settings
from core.constants import AllureFeature, AllureTitle, AssertMessage, ScenarioStep
from core.data_loader import SearchCase
from pages.cart_page import CartPage
from services.auth_service import UserSession
from services.cart_service import CartService
from services.search_service import SearchService


@pytest.mark.e2e
@allure.feature(AllureFeature.SCENARIO)
@allure.severity(allure.severity_level.CRITICAL)
@allure.title(AllureTitle.CART_BUDGET)
def test_cart_total_not_exceeds_budget(
    page: Page, settings: Settings, user_session: UserSession, search_case: SearchCase
) -> None:
    """Spec 5.5, one run per data row: search under a price, add the items, cart total <= budget * items added.

    The session (spec 5.1, guest by default) is ready before the test body: see the ``user_session`` fixture.
    """
    with allure.step(ScenarioStep.SEARCH):
        urls = SearchService(page, settings).search_items_by_name_under_price(
            search_case.query, search_case.max_price, search_case.limit
        )
        # Fewer than `limit` is valid, but 0 leaves nothing to check in the cart.
        assert urls, AssertMessage.NO_ITEMS_FOUND.format(query=search_case.query, max_price=search_case.max_price)

    cart = CartService(page, settings)
    with allure.step(ScenarioStep.ADD_TO_CART.format(count=len(urls))):
        cart.add_items_to_cart(urls)

    with allure.step(ScenarioStep.ASSERT_TOTAL):
        cart.assert_cart_total_not_exceeds(search_case.budget, len(urls))

        # Left on the cart page. Fresh context per test, so it holds exactly the items added above.
        lines = CartPage(page, settings).lines()
        assert len(lines) == len(urls), AssertMessage.CART_LINES.format(actual=len(lines), expected=len(urls))
