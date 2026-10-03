"""CartService flow with stubbed pages (no browser needed): retries, tab cleanup, cart count."""

from dataclasses import replace

import pytest

from components.variant_selector import VariantChoice
from core.config import Settings, load_settings
from core.exceptions import AddToCartError, VariantSelectionError
from services import cart_service
from services.cart_service import CartService


class FakeTab:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


class FakeSearchTab:
    url = "https://www.ebay.com/sch/i.html?_nkw=tee"

    def __init__(self) -> None:
        self.brought_to_front = 0

    def bring_to_front(self) -> None:
        self.brought_to_front += 1


class FakeHeader:
    def __init__(self, count: int) -> None:
        self.count = count
        self.waited_above: list[int] = []

    def cart_count(self) -> int:
        return self.count

    def wait_for_cart_count_above(self, count: int) -> int:
        self.waited_above.append(count)
        return count + 1


class FakeDialog:
    def close(self) -> None:
        pass


class FakeItemPage:
    """Fails ``add_to_cart`` with each error in ``failures``, then succeeds."""

    def __init__(self, failures: list[Exception], header: FakeHeader) -> None:
        self.failures = list(failures)
        self.page = FakeTab()
        self.header = header
        self.added_dialog = FakeDialog()
        self.opened: list[str] = []
        self.calls: list[str] = []
        self.screenshots: list[str] = []

    def open_listing(self, url: str) -> "FakeItemPage":
        self.opened.append(url)
        return self

    def select_random_variants(self, rng: object) -> list[VariantChoice]:
        self.calls.append("select")
        return [VariantChoice("Size", "M")]

    def keep_quantity_at_one(self) -> None:
        self.calls.append("quantity")

    def title_text(self) -> str:
        self.calls.append("title")
        return "Tee"

    def price_text(self) -> str:
        self.calls.append("price")
        return "ILS 59.37"

    def add_to_cart(self) -> str:
        self.calls.append("add")
        if self.failures:
            raise self.failures.pop(0)
        return "Added to cart"

    def take_screenshot(self, name: str, full_page: bool = False) -> None:
        self.screenshots.append(name)


@pytest.fixture
def settings() -> Settings:
    settings = load_settings("ci")
    return replace(settings, cart=replace(settings.cart, random_seed=7, variant_attempts=3))


def make_service(
    settings: Settings, monkeypatch: pytest.MonkeyPatch, items: list[FakeItemPage], header: FakeHeader
) -> tuple[CartService, FakeSearchTab]:
    search_tab = FakeSearchTab()
    service = CartService(page=search_tab, settings=settings)  # type: ignore[arg-type]
    tabs = iter(items)
    monkeypatch.setattr(service, "_open_item_tab", lambda: next(tabs))
    monkeypatch.setattr(cart_service, "Header", lambda page, settings: header)
    monkeypatch.setattr(cart_service, "attach_text", lambda *args: None)
    return service, search_tab


def test_retries_rejected_variants_on_a_fresh_page(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
    header = FakeHeader(0)
    item = FakeItemPage([VariantSelectionError("eBay asks to select: Size")] * 2, header)
    service, _ = make_service(settings, monkeypatch, [item], header)

    added = service.add_items(["https://www.ebay.com/itm/1"])

    assert item.calls.count("add") == 3
    assert item.opened == ["https://www.ebay.com/itm/1"] * 3  # first open + one reload per retry
    assert added[0].variants == (VariantChoice("Size", "M"),)


def test_gives_up_after_variant_attempts_with_the_last_error(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    header = FakeHeader(0)
    errors = [VariantSelectionError(f"attempt {n}") for n in (1, 2, 3, 4)]
    item = FakeItemPage(errors, header)
    service, search_tab = make_service(settings, monkeypatch, [item], header)

    with pytest.raises(VariantSelectionError, match="attempt 3"):
        service.add_items(["https://www.ebay.com/itm/1"])

    assert item.calls.count("add") == 3
    assert item.screenshots == ["cart_item_1_failed"]
    assert item.page.closed
    assert search_tab.brought_to_front == 1


def test_other_add_to_cart_errors_are_not_retried(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
    header = FakeHeader(0)
    item = FakeItemPage([AddToCartError("No 'Add to cart' button")], header)
    service, _ = make_service(settings, monkeypatch, [item], header)

    with pytest.raises(AddToCartError, match="No 'Add to cart' button"):
        service.add_items(["https://www.ebay.com/itm/1"])

    assert item.calls.count("add") == 1
    assert item.page.closed


def test_every_item_tab_is_closed_and_the_cart_count_carries_over(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The baseline comes from the search tab, then each add must raise it by one.
    header = FakeHeader(2)
    items = [FakeItemPage([], header) for _ in range(3)]
    service, search_tab = make_service(settings, monkeypatch, items, header)

    added = service.add_items([f"https://www.ebay.com/itm/{n}" for n in range(3)])

    assert header.waited_above == [2, 3, 4]
    assert [item.cart_count for item in added] == [3, 4, 5]
    assert all(item.page.closed for item in items)
    assert search_tab.brought_to_front == 3
    assert [item.screenshots for item in items] == [["cart_item_1"], ["cart_item_2"], ["cart_item_3"]]


def test_title_and_price_are_read_before_the_click(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
    # "Add to cart" may open the cart page, where the item title and price are gone.
    header = FakeHeader(0)
    item = FakeItemPage([], header)
    service, _ = make_service(settings, monkeypatch, [item], header)

    added = service.add_items(["https://www.ebay.com/itm/1"])

    assert item.calls == ["select", "quantity", "title", "price", "add"]
    assert (added[0].title, added[0].price) == ("Tee", "ILS 59.37")
