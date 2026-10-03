"""The search-card XPaths, checked offline against markup copied from a live eBay results page."""

from collections.abc import Iterator

import pytest
from playwright.sync_api import Page, sync_playwright

from core.config import Settings, load_settings
from pages.search_results_page import SearchResultItem, SearchResultsPage
from utils.price_parser import Price


def card(listing_id: str, title: str, *rows: str) -> str:
    return f"""
    <li class="s-card s-card--vertical" data-listingid="{listing_id}">
      <a class="s-card__link image-treatment" href="https://www.ebay.com/itm/{listing_id}?_skw=x&amp;hash=1"><img></a>
      <a class="s-card__link" href="https://www.ebay.com/itm/{listing_id}?_skw=x&amp;itmmeta=abc">
        <div role="heading" class="s-card__title"><span class="su-styled-text primary default">{title}</span><span class="clipped">Opens in a new window or tab</span></div>
      </a>
      {"".join(rows)}
    </li>"""


def price_row(*spans: str) -> str:
    return f'<div class="s-card__attribute-row">{"".join(spans)}</div>'


def price(text: str) -> str:
    return f'<span class="su-styled-text primary bold large-1 s-card__price">{text}</span>'


def info_row(text: str) -> str:
    return price_row(f'<span class="su-styled-text secondary large">{text}</span>')


RESULTS_HTML = f"""
<ul class="srp-results srp-grid clearfix">
  {card("101", "Plain shoe", price_row(price("ILS 138.31")), info_row("+ILS 20.39 delivery"))}
  {card("102", "Range shoe", price_row(price("ILS 81.50"), price(" to "), price("ILS 110.86")))}
  {card("103", "Sale shoe", price_row(price("ILS 139.66"), '<span class="su-styled-text secondary strikethrough large">ILS 164.31</span>'))}
  {card("104", "Auction shoe", price_row(price("ILS 40.77")), info_row("0 bids"))}
  {card("105", "Auction with BIN", price_row(price("ILS 40.77")), info_row("2 bids"), price_row(price("ILS 101.93")), info_row("Buy It Now"))}
  <li class="srp-river-answer srp-river-answer--NAVIGATION_ANSWER_COLLAPSIBLE_CAROUSEL">Popular Filters</li>
  {card("123456", "Shop on eBay", price_row(price("$20.00")))}
  <li class="s-card s-card--vertical"><div class="s-card__title"><span>No listing id</span></div></li>
  {card("106", "No price shoe")}
  <li class="srp-river-answer srp-river-answer--REWRITE_START">Results matching fewer words</li>
  {card("107", "Fewer words shoe", price_row(price("ILS 10.00")))}
</ul>
"""


# A "0 results" page (seen live, 2026-10): the "No exact matches found" block comes
# before the list, and the list is still filled with fuzzy matches.
NO_MATCH_HTML = f"""
<div id="srp-river-results" class="srp-river-results clearfix">
  <div class="srp-river-answer srp-river-answer--SAVE_CARD"><div class="srp-save-null-search">
    <h3 class="srp-save-null-search__heading">No exact matches found</h3></div></div>
  <ul class="srp-results srp-list clearfix">
    {card("201", "LAMP SOCKET T5 T10 HB3 H7", price_row(price("ILS 12.00")))}
    {card("202", "Hynix 2GB Server RAM H9-T7", price_row(price("ILS 30.00")))}
  </ul>
</div>
"""


@pytest.fixture(scope="module")
def settings() -> Settings:
    return load_settings("ci")


@pytest.fixture(scope="module")
def page() -> Iterator[Page]:
    # Local HTML only: no eBay traffic, so headless is fine here.
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_content(RESULTS_HTML)
        yield page
        browser.close()


@pytest.fixture(scope="module")
def items(page: Page, settings: Settings) -> dict[str, SearchResultItem]:
    return {item.listing_id: item for item in SearchResultsPage(page, settings).items()}


def test_only_real_listings_before_the_fewer_words_divider(items: dict[str, SearchResultItem]) -> None:
    assert list(items) == ["101", "102", "103", "104", "105", "106"]


def test_title_without_hidden_suffix_and_clean_url(items: dict[str, SearchResultItem]) -> None:
    item = items["101"]

    assert item.title == "Plain shoe"
    assert item.url == "https://www.ebay.com/itm/101"
    assert item.price == Price(138.31, 138.31, "ILS")
    assert item.auction_only is False


def test_range_split_over_spans_is_read_as_range(items: dict[str, SearchResultItem]) -> None:
    assert items["102"].price == Price(81.5, 110.86, "ILS")


def test_crossed_out_price_is_ignored(items: dict[str, SearchResultItem]) -> None:
    assert items["103"].price == Price(139.66, 139.66, "ILS")


def test_auction_only_is_flagged(items: dict[str, SearchResultItem]) -> None:
    assert items["104"].auction_only is True


def test_auction_with_buy_it_now_uses_the_higher_price(items: dict[str, SearchResultItem]) -> None:
    item = items["105"]

    assert item.auction_only is False
    assert item.price is not None and item.price.high == 101.93


def test_card_without_price_has_none(items: dict[str, SearchResultItem]) -> None:
    assert items["106"].price is None


def test_no_items_on_a_zero_results_page(page: Page, settings: Settings) -> None:
    """eBay fills a "0 results" page with fuzzy matches; none of them is a result for the query."""
    page.set_content(NO_MATCH_HTML)
    try:
        assert SearchResultsPage(page, settings).items() == []
    finally:
        page.set_content(RESULTS_HTML)  # the module-scoped page is shared with the tests above
