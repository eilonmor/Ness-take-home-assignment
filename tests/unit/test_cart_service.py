"""CartService flow with stubbed pages (no browser needed): retries, tab cleanup, cart count, budget check."""

from dataclasses import replace

import pytest

from components.variant_selector import VariantChoice
from core.config import Settings, load_settings
from core.exceptions import AddToCartError, CartBudgetExceededError, VariantSelectionError
from pages.cart_page import CartLine
from services import cart_service
from services.cart_service import CartCheck, CartService
from utils.price_parser import Price


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


# --- assert_cart_total_not_exceeds (spec 5.4) ----------------------------------


class FakeContext:
    def __init__(self) -> None:
        self.tracing = self
        self.groups: list[str] = []

    def group(self, name: str) -> None:
        self.groups.append(name)

    def group_end(self) -> None:
        self.groups.append("end")


class FakeCartTab(FakeSearchTab):
    def __init__(self) -> None:
        super().__init__()
        self.context = FakeContext()


class FakeCartHeader:
    def __init__(self) -> None:
        self.opened = 0

    def open_cart(self) -> None:
        self.opened += 1


class FakeCartPage:
    def __init__(self, totals: dict[str, Price], lines: int) -> None:
        self.totals = totals
        self._lines = [CartLine(f"Item {n}", "ILS 10.00", 1) for n in range(lines)]
        self.screenshots: list[tuple[str, bool]] = []

    def wait_until_loaded(self) -> "FakeCartPage":
        return self

    def total(self, line: str) -> Price:
        return self.totals[line]

    def lines(self) -> list[CartLine]:
        return self._lines

    def take_screenshot(self, name: str, full_page: bool = False) -> None:
        self.screenshots.append((name, full_page))


def ils(amount: float) -> Price:
    return Price(amount, amount, "ILS")


def make_cart_service(
    settings: Settings, monkeypatch: pytest.MonkeyPatch, cart: FakeCartPage
) -> tuple[CartService, FakeCartTab, FakeCartHeader, list[str]]:
    tab, header, attached = FakeCartTab(), FakeCartHeader(), []
    monkeypatch.setattr(cart_service, "Header", lambda page, settings: header)
    monkeypatch.setattr(cart_service, "CartPage", lambda page, settings: cart)
    monkeypatch.setattr(cart_service, "attach_text", lambda content, name: attached.append(content))
    return CartService(page=tab, settings=settings), tab, header, attached  # type: ignore[arg-type]


def test_total_within_budget_passes_with_evidence(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
    cart = FakeCartPage({"items": ils(600.0), "subtotal": ils(700.0)}, lines=3)
    service, tab, header, attached = make_cart_service(settings, monkeypatch, cart)

    service.assert_cart_total_not_exceeds(220, 3)

    assert header.opened == 1
    assert cart.screenshots == [("cart_page", True)]
    assert tab.context.groups == ["Cart page", "end"]
    assert "Budget: 220 per item x 3 items = 660.00" in attached[0]
    assert "Result: OK" in attached[0]


def test_total_equal_to_budget_passes(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
    # 3 x 0.1 is 0.30000000000000004 in floats; the check is in cents.
    cart = FakeCartPage({"items": ils(0.3)}, lines=3)
    service, *_ = make_cart_service(settings, monkeypatch, cart)

    service.assert_cart_total_not_exceeds(0.1, 3)


def test_total_above_budget_fails_with_actual_vs_budget(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
    cart = FakeCartPage({"items": ils(675.5)}, lines=3)
    service, _, _, attached = make_cart_service(settings, monkeypatch, cart)

    with pytest.raises(CartBudgetExceededError) as error:
        service.assert_cart_total_not_exceeds(220, 3)

    assert str(error.value) == (
        "Cart items ILS 675.50 is above the budget 660.00 (220 per item x 3 items), over by 15.50"
    )
    assert isinstance(error.value, AssertionError)  # a failed check in pytest, not an error
    assert "Result: ABOVE BUDGET" in attached[0]
    assert cart.screenshots, "the cart screenshot is taken before the check fails"


def test_total_line_comes_from_the_profile(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
    # Items fit the budget; with shipping (subtotal) they do not.
    cart = FakeCartPage({"items": ils(600.0), "subtotal": ils(700.0)}, lines=3)
    subtotal_settings = replace(settings, cart=replace(settings.cart, total_line="subtotal"))
    service, *_ = make_cart_service(subtotal_settings, monkeypatch, cart)

    with pytest.raises(CartBudgetExceededError, match="^Cart subtotal ILS 700.00"):
        service.assert_cart_total_not_exceeds(220, 3)


def test_no_trace_group_when_tracing_is_off(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
    cart = FakeCartPage({"items": ils(1.0)}, lines=1)
    no_trace = replace(settings, artifacts=replace(settings.artifacts, trace="off"))
    service, tab, *_ = make_cart_service(no_trace, monkeypatch, cart)

    service.assert_cart_total_not_exceeds(5, 1)

    assert tab.context.groups == []


def test_negative_budget_is_rejected(settings: Settings) -> None:
    service = CartService(page=FakeCartTab(), settings=settings)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="must not be negative"):
        service.assert_cart_total_not_exceeds(-1, 3)


def test_cart_check_report_lists_every_line() -> None:
    lines = (CartLine("Tee", "US $16.25 (ILS 59.37)", 1), CartLine("Cable", "ILS 12.50", 1))
    check = CartCheck("items", ils(71.87), 50, 2, lines)

    assert str(check).splitlines()[-2:] == [
        "1. 1 x US $16.25 (ILS 59.37) | Tee",
        "2. 1 x ILS 12.50 | Cable",
    ]
