"""Which result cards count as a match (no browser needed)."""

import pytest

from core.config import Settings, load_settings
from pages.search_results_page import SearchResultItem
from services.search_service import SearchService
from utils.price_parser import Price


def item(listing_id: str, high: float | None, *, auction_only: bool = False, low: float | None = None) -> SearchResultItem:
    price = None if high is None else Price(high if low is None else low, high, "USD")
    return SearchResultItem(listing_id, f"Item {listing_id}", f"https://www.ebay.com/itm/{listing_id}", price, auction_only)


@pytest.fixture
def service() -> SearchService:
    settings: Settings = load_settings("ci")
    return SearchService(page=None, settings=settings)  # type: ignore[arg-type]  # page unused here


def test_keeps_items_at_or_below_max_and_stops_at_wanted(service: SearchService) -> None:
    items = [item("1", 219.99), item("2", 220.0), item("3", 50.0), item("4", 10.0)]

    matches = service._matching_items(items, max_price=220, wanted=3, seen_urls=set())

    assert [match.listing_id for match in matches] == ["1", "2", "3"]


def test_skips_expensive_auction_only_unpriced_and_duplicates(service: SearchService) -> None:
    seen = {"https://www.ebay.com/itm/dup"}
    items = [
        item("over", 220.01),
        item("range-over", 300.0, low=100.0),  # upper bound counts
        item("auction", 10.0, auction_only=True),
        item("no-price", None),
        item("dup", 10.0),
        item("ok", 99.0),
    ]

    matches = service._matching_items(items, max_price=220, wanted=5, seen_urls=seen)

    assert [match.listing_id for match in matches] == ["ok"]
    assert "https://www.ebay.com/itm/ok" in seen


def test_limit_must_be_positive(service: SearchService) -> None:
    with pytest.raises(ValueError, match="limit must be at least 1"):
        service.find_items_under_price("shoes", 220, limit=0)
