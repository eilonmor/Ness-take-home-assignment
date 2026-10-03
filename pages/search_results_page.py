"""eBay search results (/sch/i.html): price filter, item cards, paging."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from playwright.sync_api import Page

from components.header import Header
from components.pagination import Pagination
from components.price_filter import PriceFilter
from core.base_page import BasePage
from core.config import Settings
from core.constants import RESULTS_TYPE_NO_CACHE, Endpoints, QueryParam, Waits
from core.constants import SearchResultsXPaths as XPaths
from utils.price_parser import Price, PriceParseError, parse_price
from utils.urls import with_query, without_query

# Reads every card in one round trip, using XPaths.CARD_FIELDS.
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
    path = Endpoints.SEARCH

    def __init__(self, page: Page, settings: Settings) -> None:
        super().__init__(page, settings)
        self.header = Header(page, settings)
        self.price_filter = PriceFilter(page, settings)
        self.pagination = Pagination(page, settings)
        self.item_cards = page.locator(f"{XPaths.PREFIX}{XPaths.ITEM_CARDS}")
        self.results_or_empty = page.locator(f"{XPaths.PREFIX}{XPaths.RESULTS_LIST} | {XPaths.NO_RESULTS}").first

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
        cards: list[dict[str, Any]] = self.item_cards.evaluate_all(_READ_CARDS_JS, XPaths.CARD_FIELDS)
        items = [item for card in cards if (item := self._to_item(card)) is not None]
        self.log.info("Page %d: %d listing cards", self.pagination.current_page, len(items))
        return items

    def _apply_max_price_via_url(self, max_price: float) -> None:
        self.log.warning("No price filter box on the page; setting %s in the URL instead", QueryParam.MAX_PRICE)
        params = {
            QueryParam.MAX_PRICE: str(math.ceil(max_price)),
            QueryParam.RESULTS_TYPE: RESULTS_TYPE_NO_CACHE,
            QueryParam.PAGE: None,
        }
        url = with_query(self.page.url, **params)
        self.page.goto(url, wait_until=Waits.NAVIGATION_WAIT_UNTIL)
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
