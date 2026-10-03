"""eBay cart (cart.ebay.com): line items and the order summary totals."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Self

from playwright.sync_api import Locator, Page

from core.base_page import BasePage
from core.config import Settings
from core.constants import CartPageLocators as Locators
from core.constants import CartTotalLine
from core.exceptions import CartReadError
from utils.price_parser import Price, PriceParseError, parse_price


@dataclass(frozen=True)
class CartLine:
    title: str
    # As shown on the line, in the listing's currency, e.g. "US $68.99 (ILS 210.70)".
    price: str
    quantity: int

    def __str__(self) -> str:
        return f"{self.quantity} x {self.price} | {self.title}"


class CartPage(BasePage):
    """Reached through ``Header.open_cart()``: the cart lives on another host than
    ``base_url``, and a cold deep link is more likely to get a bot check."""

    def __init__(self, page: Page, settings: Settings) -> None:
        super().__init__(page, settings)
        self.summary = page.locator(Locators.SUMMARY)
        self.item_total = self.summary.locator(Locators.ITEM_TOTAL)
        self.subtotal = self.summary.locator(Locators.SUBTOTAL)
        self.line_items = page.locator(Locators.LINE_ITEM)

    def wait_until_loaded(self) -> Self:
        """The summary is rendered with the totals; an empty cart has neither."""
        self.ensure_not_blocked()
        self.wait_until_visible(self.subtotal)
        return self

    def total(self, line: str = CartTotalLine.ITEMS) -> Price:
        """The order summary row ``line`` (``CartTotalLine``), parsed."""
        return self._read_price(self.item_total if line == CartTotalLine.ITEMS else self.subtotal, line)

    def lines(self) -> list[CartLine]:
        return [self._read_line(line) for line in self.line_items.all()]

    def _read_line(self, line: Locator) -> CartLine:
        quantity = line.locator(Locators.LINE_QUANTITY)
        # No quantity box when the seller has a single unit.
        units = int(quantity.input_value()) if quantity.count() else 1
        return CartLine(
            title=line.locator(Locators.LINE_TITLE).inner_text().strip(),
            price=" ".join(line.locator(Locators.LINE_PRICE).inner_text().split()),
            quantity=units,
        )

    def _read_price(self, locator: Locator, line: str) -> Price:
        text = self.text_of(locator)
        try:
            price = parse_price(text)
        except PriceParseError as error:
            raise CartReadError(f"Cannot read the cart {line} {text!r}: {error}") from None
        if price is None:
            raise CartReadError(f"The cart {line} shows no price: {text!r}")
        return price
