"""CartPage locators, checked offline against markup copied from the live cart page (cart.ebay.com, 2026-10)."""

from collections.abc import Iterator

import pytest
from playwright.sync_api import Page, sync_playwright

from core.config import Settings, load_settings
from core.exceptions import CartReadError
from pages.cart_page import CartLine, CartPage
from utils.price_parser import Price


def line_item(title: str, price: str, converted: str, quantity: str | None) -> str:
    quantity_box = (
        f'<div class="quantity"><span class="number-input"><span class="textbox">'
        f'<input aria-label="Quantity" class="textbox__control" type="number" value="{quantity}"></span></span></div>'
        if quantity
        else ""
    )
    return f"""
    <li><div class="cart-bucket-lineitem"><div class="listsummary" data-test-id="list-summary">
      <h3 class="item-title"><a href="https://www.ebay.com/itm/1" data-test-id="cart-item-link">{title}</a></h3>
      <div class="price-details"><div class="item-price font-title-2"><span><span>{price}</span></span></div>
        <div class="additional-prices"><div><span>{converted}</span></div></div></div>
      <div class="line-item-foot"><div class="grid-item-quantity">{quantity_box}</div></div>
    </div></div></li>"""


def summary_row(label: str, test_id: str, value: str) -> str:
    return (
        f'<div class="cart-summary-line-item"><div><span>{label}</span></div>'
        f'<div class="val-col" data-test-id="{test_id}"><span><span>{value}</span></span></div></div>'
    )


def cart_html(item_total: str, subtotal: str) -> str:
    return f"""
    <h1 class="main-title" data-test-id="main-title">Cart</h1>
    <div data-test-id="cart-bucket"><ul class="cart-bucket__vendor-list">
      {line_item("New Balance Fresh Foam X 880v15", "US $68.99", "(ILS 210.70)", "1")}
      {line_item("USB C cable 2 pack", "ILS 12.50", "", None)}
    </ul></div>
    <div class="cartsummary" data-test-id="cart-summary"><h2>Order summary</h2><div class="table">
      {summary_row("Items (2)", "ITEM_TOTAL", item_total)}
      {summary_row("Shipping", "SHIPPING", "ILS 30.00")}
      {summary_row("Subtotal", "SUBTOTAL", subtotal)}
    </div></div>"""


@pytest.fixture(scope="module")
def settings() -> Settings:
    return load_settings("ci")


@pytest.fixture(scope="module")
def page() -> Iterator[Page]:
    # Local HTML only: no eBay traffic, so headless is fine here.
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        yield browser.new_page()
        browser.close()


def cart(page: Page, settings: Settings, item_total: str = "ILS 223.20", subtotal: str = "ILS 253.20") -> CartPage:
    page.set_content(cart_html(item_total, subtotal))
    return CartPage(page, settings).wait_until_loaded()


def test_reads_the_items_row_and_the_subtotal_row(page: Page, settings: Settings) -> None:
    cart_page = cart(page, settings)

    assert cart_page.total("items") == Price(223.20, 223.20, "ILS")
    assert cart_page.total("subtotal") == Price(253.20, 253.20, "ILS")


def test_lines_keep_both_prices_and_default_to_one_unit(page: Page, settings: Settings) -> None:
    assert cart(page, settings).lines() == [
        CartLine("New Balance Fresh Foam X 880v15", "US $68.99 (ILS 210.70)", 1),
        CartLine("USB C cable 2 pack", "ILS 12.50", 1),
    ]


def test_thousands_separator_in_the_total(page: Page, settings: Settings) -> None:
    assert cart(page, settings, item_total="ILS 1,234.50").total("items").high == 1234.50


@pytest.mark.parametrize("text", ["-", "ILS 12.50 ILS 3.00"])
def test_unreadable_total_raises(page: Page, settings: Settings, text: str) -> None:
    with pytest.raises(CartReadError, match="items"):
        cart(page, settings, item_total=text).total("items")
