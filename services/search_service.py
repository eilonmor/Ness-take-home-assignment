"""Search flow: query -> price filter -> collect matching items across result pages."""

from __future__ import annotations

import allure
from playwright.sync_api import Page

from components.header import Header
from core.config import Settings
from core.logger import get_logger
from pages.search_results_page import SearchResultItem, SearchResultsPage
from utils.attachments import attach_text


class SearchService:
    def __init__(self, page: Page, settings: Settings) -> None:
        self.page = page
        self.settings = settings
        self.log = get_logger(type(self).__name__)
        self._currency_warned = False

    def search_items_by_name_under_price(self, query: str, max_price: float, limit: int = 5) -> list[str]:
        """URLs of up to ``limit`` items priced <= ``max_price`` (fewer, even 0, is valid). Spec 5.2."""
        return [item.url for item in self.find_items_under_price(query, max_price, limit)]

    def find_items_under_price(self, query: str, max_price: float, limit: int = 5) -> list[SearchResultItem]:
        """Like ``search_items_by_name_under_price``, but keeps title and price for checks and reports.

        Starts from the page the session is on (the search box is in the
        header) and pages through results until ``limit`` items are found, the
        pages run out, or ``search.max_pages`` is reached.
        """
        if limit < 1:
            raise ValueError(f"limit must be at least 1, got {limit}")

        with allure.step(f"Search '{query}' for up to {limit} items priced <= {max_price:g}"):
            Header(self.page, self.settings).search(query)
            results = SearchResultsPage(self.page, self.settings)
            with allure.step(f"Apply the price filter: max {max_price:g}"):
                results.apply_max_price(max_price)

            found: list[SearchResultItem] = []
            seen_urls: set[str] = set()
            while True:
                page_number = results.pagination.current_page
                with allure.step(f"Collect items from results page {page_number}"):
                    found += self._matching_items(results.items(), max_price, limit - len(found), seen_urls)
                    results.take_screenshot(f"search_{query}_page_{page_number}")
                if len(found) >= limit:
                    break
                if not results.pagination.has_next():
                    self.log.info("No more result pages after page %d", page_number)
                    break
                if page_number >= self.settings.search.max_pages:
                    self.log.warning("Stopped at the search.max_pages limit (%d)", self.settings.search.max_pages)
                    break
                results.pagination.go_next()

        self.log.info("Found %d/%d items for %r priced <= %g", len(found), limit, query, max_price)
        attach_text(_summary(found), f"Items found for '{query}' (<= {max_price:g})")
        return found

    def _matching_items(
        self, items: list[SearchResultItem], max_price: float, wanted: int, seen_urls: set[str]
    ) -> list[SearchResultItem]:
        matches: list[SearchResultItem] = []
        for item in items:
            if len(matches) == wanted:
                break
            reason = self._skip_reason(item, max_price, seen_urls)
            if reason:
                self.log.debug("Skip %s (%s): %s", item.listing_id, reason, item.title)
                continue
            seen_urls.add(item.url)
            matches.append(item)
            self.log.info("Match %s: %s | %s", item.price, item.title, item.url)
        return matches

    def _skip_reason(self, item: SearchResultItem, max_price: float, seen_urls: set[str]) -> str | None:
        if item.url in seen_urls:
            return "already collected"
        if item.auction_only:
            return "auction only, cannot be added to the cart"
        if item.price is None:
            return "no readable price"
        self._warn_on_currency_mismatch(item)
        if item.price.high > max_price:
            return f"price {item.price} above {max_price:g}"
        return None

    def _warn_on_currency_mismatch(self, item: SearchResultItem) -> None:
        currency = item.price.currency if item.price else None
        if currency and currency != self.settings.currency and not self._currency_warned:
            self._currency_warned = True
            self.log.warning(
                "eBay shows prices in %s, not the profile's %s (it localizes by visitor region); "
                "max_price is compared in %s",
                currency,
                self.settings.currency,
                currency,
            )


def _summary(items: list[SearchResultItem]) -> str:
    if not items:
        return "No matching items."
    return "\n".join(f"{index}. {item.price} | {item.title}\n   {item.url}" for index, item in enumerate(items, 1))
