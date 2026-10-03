"""eBay search results (/sch/i.html): price filter, item cards, paging."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from playwright.sync_api import Page

from components.header import Header
from components.pagination import Pagination
from components.price_filter import MAX_PRICE_PARAM, PriceFilter
from core.base_page import BasePage
from core.config import Settings
from utils.price_parser import Price, PriceParseError, parse_price
from utils.urls import with_query, without_query


def _has_class(name: str) -> str:
    """XPath test for one whole class token (``contains(@class, 's-card')`` would also match 's-card__title')."""
    return f"contains(concat(' ', normalize-space(@class), ' '), ' {name} ')"


# --- XPath locators (spec 5.2) -------------------------------------------
RESULTS_LIST = f"//ul[{_has_class('srp-results')}]"
# Real listings only. Skipped: carousels / filter / paging rows (srp-river-answer),
# the "Shop on eBay" placeholder card, and everything after the "Results matching
# fewer words" divider (those cards do not match the query).
ITEM_CARDS = (
    f"{RESULTS_LIST}/li[{_has_class('s-card')}][@data-listingid]"
    "[not(starts-with(normalize-space(.//*[contains(@class, 's-card__title')]), 'Shop on eBay'))]"
    "[not(preceding-sibling::li[contains(@class, 'srp-river-answer--REWRITE_START')])]"
)
NO_RESULTS = "//*[contains(@class, 'srp-save-null-search')]"
# Relative to a card:
CARD_XPATHS = {
    # The title also holds a visually hidden "Opens in a new window or tab" span.
    "title": ".//*[contains(@class, 's-card__title')]/span[not(contains(@class, 'clipped'))]",
    "link": ".//a[contains(@class, 's-card__link')][contains(@href, '/itm/')]",
    # One row per price: a range is three spans in one row ("$1" " to " "$2");
    # an auction with Buy It Now has a bid row and a Buy It Now row. The crossed-out
    # "was" price sits in the same row with another class, so it is not selected.
    "price_rows": f".//div[{_has_class('s-card__attribute-row')}][span[contains(@class, 's-card__price')]]",
    "price_parts": "./span[contains(@class, 's-card__price')]",
    "bids": f".//div[{_has_class('s-card__attribute-row')}]/span[contains(., ' bid')]",
    "buy_it_now": f".//div[{_has_class('s-card__attribute-row')}]/span[normalize-space() = 'Buy It Now']",
}

# Reads every card in one round trip, using the XPaths above.
_READ_CARDS_JS = """
(cards, xpaths) => {
  const all = (node, xpath) => {
    const found = document.evaluate(xpath, node, null, XPathResult.ORDERED_NODE_SNAPSHOT_TYPE, null);
    return Array.from({ length: found.snapshotLength }, (_, i) => found.snapshotItem(i));
  };
  const text = (node) => (node ? node.textContent.replace(/\\s+/g, " ").trim() : "");
  return cards.map((card) => ({
    listingId: card.getAttribute("data-listingid"),
    title: text(all(card, xpaths.title)[0]),
    href: all(card, xpaths.link)[0]?.href ?? null,
    priceRows: all(card, xpaths.price_rows).map((row) => all(row, xpaths.price_parts).map(text).join(" ")),
    hasBids: all(card, xpaths.bids).length > 0,
    hasBuyItNow: all(card, xpaths.buy_it_now).length > 0,
  }));
}
"""


@dataclass(frozen=True)
class SearchResultItem:
    listing_id: str
    title: str
    url: str
    # Highest price the card shows (range upper bound, or the Buy It Now
    # price of an auction); None when no price could be read.
    price: Price | None
    # Bidding only, no Buy It Now: such an item cannot be added to the cart.
    auction_only: bool


class SearchResultsPage(BasePage):
    path = "/sch/i.html"

    def __init__(self, page: Page, settings: Settings) -> None:
        super().__init__(page, settings)
        self.header = Header(page, settings)
        self.price_filter = PriceFilter(page, settings)
        self.pagination = Pagination(page, settings)
        self.item_cards = page.locator(f"xpath={ITEM_CARDS}")
        self.results_or_empty = page.locator(f"xpath={RESULTS_LIST} | {NO_RESULTS}").first

    def wait_for_results(self) -> None:
        self.results_or_empty.wait_for(state="attached")

    def apply_max_price(self, max_price: float) -> None:
        """Narrow the results with the sidebar price box; edit the URL if the box is missing."""
        self.wait_for_results()
        if self.price_filter.is_available():
            self.price_filter.apply_max(max_price)
        else:
            self._apply_max_price_via_url(max_price)
        self.wait_for_results()

    def items(self) -> list[SearchResultItem]:
        """The listing cards on the current page, in display order."""
        self.wait_for_results()
        cards: list[dict[str, Any]] = self.item_cards.evaluate_all(_READ_CARDS_JS, CARD_XPATHS)
        items = [item for card in cards if (item := self._to_item(card)) is not None]
        self.log.info("Page %d: %d listing cards", self.pagination.current_page, len(items))
        return items

    def _apply_max_price_via_url(self, max_price: float) -> None:
        self.log.warning("No price filter box on the page; setting %s in the URL instead", MAX_PRICE_PARAM)
        url = with_query(self.page.url, **{MAX_PRICE_PARAM: str(math.ceil(max_price)), "rt": "nc", "_pgn": None})
        self.page.goto(url, wait_until="domcontentloaded")
        self.ensure_not_blocked()

    def _to_item(self, card: dict[str, Any]) -> SearchResultItem | None:
        if not card["href"]:
            self.log.debug("Skipping card %s: no item link", card["listingId"])
            return None
        return SearchResultItem(
            listing_id=card["listingId"],
            title=card["title"],
            url=without_query(card["href"]),
            price=self._card_price(card["priceRows"], card["listingId"]),
            auction_only=card["hasBids"] and not card["hasBuyItNow"],
        )

    def _card_price(self, rows: list[str], listing_id: str) -> Price | None:
        try:
            prices = [price for row in rows if (price := parse_price(row)) is not None]
        except PriceParseError as error:
            self.log.warning("Card %s: unreadable price, skipping it: %s", listing_id, error)
            return None
        if not prices:
            return None
        return Price(
            low=min(price.low for price in prices),
            high=max(price.high for price in prices),
            currency=prices[0].currency,
        )
