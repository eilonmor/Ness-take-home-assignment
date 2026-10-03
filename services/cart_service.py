"""Cart flow: add items with random available variants, then check the cart total against the budget."""

from __future__ import annotations

import random
from dataclasses import dataclass

import allure
from playwright.sync_api import Page

from components.header import Header
from components.variant_selector import VariantChoice
from core.config import Settings
from core.constants import SEED_UPPER_BOUND, AssertMessage, AttachmentName, EnvVar, ScreenshotName, TraceMode
from core.exceptions import CartBudgetExceededError, VariantSelectionError
from core.logger import get_logger
from pages.cart_page import CartLine, CartPage
from pages.item_page import ItemPage
from utils.attachments import attach_text
from utils.price_parser import Price
from utils.tracing import tracing_group


@dataclass(frozen=True)
class CartItem:
    url: str
    title: str
    # As shown on the item page for the chosen variant, e.g. "ILS 59.37".
    price: str
    variants: tuple[VariantChoice, ...]
    cart_count: int

    def __str__(self) -> str:
        variants = ", ".join(map(str, self.variants)) or "no variants"
        return f"{self.price} | {self.title} | {variants}\n   {self.url}"


@dataclass(frozen=True)
class CartCheck:
    """The cart total next to the budget it is checked against (spec 5.4)."""

    line: str  # CartTotalLine: which order summary row ``total`` was read from
    total: Price
    budget_per_item: float
    items_count: int
    lines: tuple[CartLine, ...]

    @property
    def budget(self) -> float:
        return self.budget_per_item * self.items_count

    @property
    def within_budget(self) -> bool:
        # Cents: 3 x 0.1 must not end up above 0.3.
        return round(self.total.high, 2) <= round(self.budget, 2)

    def failure_message(self) -> str:
        return AssertMessage.CART_TOTAL_ABOVE_BUDGET.format(
            line=self.line,
            total=self.total,
            budget=self.budget,
            budget_per_item=self.budget_per_item,
            items_count=self.items_count,
            excess=self.total.high - self.budget,
        )

    def __str__(self) -> str:
        verdict = "OK" if self.within_budget else "ABOVE BUDGET"
        lines = [
            f"Cart {self.line}: {self.total}",
            f"Budget: {self.budget_per_item:g} per item x {self.items_count} items = {self.budget:,.2f}",
            f"Result: {verdict}",
            f"Cart lines ({len(self.lines)}):",
        ]
        lines += [f"{index}. {line}" for index, line in enumerate(self.lines, 1)]
        return "\n".join(lines)


class CartService:
    """Adds items from the search results tab, one new tab per item.

    The results tab stays where it was, so "going back to the search" is
    closing the item tab. Variant choices come from a seeded RNG: the seed is
    logged, and ``RANDOM_SEED=<seed>`` replays the same choices.
    """

    def __init__(self, page: Page, settings: Settings) -> None:
        self.page = page
        self.settings = settings
        self.log = get_logger(type(self).__name__)
        self.seed = settings.cart.random_seed if settings.cart.random_seed is not None else random.randrange(SEED_UPPER_BOUND)
        self.rng = random.Random(self.seed)

    def add_items_to_cart(self, urls: list[str]) -> None:
        """Spec 5.3."""
        self.add_items(urls)

    def add_items(self, urls: list[str]) -> list[CartItem]:
        """Like ``add_items_to_cart``, but returns what was added for checks and reports.

        Raises ``AddToCartError`` on the first item that cannot be added: the
        cart check (budget * item count) is only meaningful when every item is in.
        """
        self.log.info("Adding %d items to the cart (variant seed %d)", len(urls), self.seed)
        added: list[CartItem] = []
        with allure.step(f"Add {len(urls)} items to the cart (variant seed {self.seed})"):
            # Read on the search tab, which is fully loaded; a new item tab may
            # not have rendered the badge yet and would report 0.
            cart_count = Header(self.page, self.settings).cart_count()
            for number, url in enumerate(urls, 1):
                added.append(self._add_item(url, number, len(urls), cart_count))
                cart_count = added[-1].cart_count
        attach_text(_summary(added, self.seed), AttachmentName.CART_ITEMS)
        return added

    def assert_cart_total_not_exceeds(self, budget_per_item: float, items_count: int) -> None:
        """Spec 5.4. Raises ``CartBudgetExceededError`` (an AssertionError) with actual vs. budget."""
        check = self.check_cart_total(budget_per_item, items_count)
        if not check.within_budget:
            raise CartBudgetExceededError(check.failure_message())

    def check_cart_total(self, budget_per_item: float, items_count: int) -> CartCheck:
        """Open the cart from the current page and read its total; the comparison is left to the caller.

        Leaves the browser on the cart page, with a full-page screenshot, the
        check attached to the report, and the steps grouped as "Cart page" in the trace.
        """
        if budget_per_item < 0 or items_count < 0:
            raise ValueError(f"budget_per_item and items_count must not be negative, got {budget_per_item}, {items_count}")
        line = self.settings.cart.total_line
        tracing_active = self.settings.artifacts.trace != TraceMode.OFF
        with (
            allure.step(f"Check the cart {line} <= {budget_per_item:g} x {items_count}"),
            tracing_group(self.page.context, "Cart page", tracing_active),
        ):
            Header(self.page, self.settings).open_cart()
            cart = CartPage(self.page, self.settings).wait_until_loaded()
            check = CartCheck(line, cart.total(line), budget_per_item, items_count, tuple(cart.lines()))
            cart.take_screenshot(ScreenshotName.CART_PAGE, full_page=True)
            attach_text(str(check), AttachmentName.CART_CHECK)

        self.log.info("Cart check:\n%s", check)
        if len(check.lines) != items_count:
            # Not part of the spec's check, but a cart with other items makes the total meaningless.
            self.log.warning(AssertMessage.CART_LINES.format(actual=len(check.lines), expected=items_count))
        return check

    def _add_item(self, url: str, number: int, total: int, cart_count_before: int) -> CartItem:
        with allure.step(f"Add item {number}/{total} to the cart: {url}"):
            item = self._open_item_tab()
            try:
                item.open_listing(url)
                variants, title, price = self._add_with_random_variants(item, url)
                cart_count = item.header.wait_for_cart_count_above(cart_count_before)
                added = CartItem(url, title, price, tuple(variants), cart_count)
                item.take_screenshot(ScreenshotName.CART_ITEM.format(number=number))
                self.log.info("Added item %d/%d (cart now %d): %s", number, total, cart_count, added)
                item.added_dialog.close()
                return added
            except Exception:
                # The tab is closed below, so the failure hook in conftest would not see it.
                self._failure_screenshot(item, number)
                raise
            finally:
                item.page.close()
                self._back_to_search()

    def _open_item_tab(self) -> ItemPage:
        return ItemPage(self.page.context.new_page(), self.settings)

    def _add_with_random_variants(self, item: ItemPage, url: str) -> tuple[list[VariantChoice], str, str]:
        """Retry with a new random combination while eBay rejects the variants (last error is raised)."""
        attempts = self.settings.cart.variant_attempts
        for attempt in range(1, attempts):
            try:
                return self._select_variants_and_add(item)
            except VariantSelectionError as error:
                self.log.warning("Variant attempt %d/%d failed, trying another combination: %s", attempt, attempts, error)
                item.open_listing(url)  # start again from a page with nothing selected
        return self._select_variants_and_add(item)

    def _select_variants_and_add(self, item: ItemPage) -> tuple[list[VariantChoice], str, str]:
        """Returns the variants, title and price; the last two are read before the click,
        because "Add to cart" may leave the item page (eBay can open the cart page instead)."""
        variants = item.select_random_variants(self.rng)
        item.keep_quantity_at_one()
        title, price = item.title_text(), item.price_text()
        self.log.info("eBay confirmed: %s", item.add_to_cart())
        return variants, title, price

    def _failure_screenshot(self, item: ItemPage, number: int) -> None:
        try:
            item.take_screenshot(ScreenshotName.CART_ITEM_FAILED.format(number=number), full_page=True)
        except Exception as error:  # best effort: never hide the original failure
            self.log.warning("Could not capture the item %d failure screenshot: %s", number, error)

    def _back_to_search(self) -> None:
        self.page.bring_to_front()
        self.log.debug("Back on the search tab: %s", self.page.url)


def _summary(items: list[CartItem], seed: int) -> str:
    lines = [f"Variant seed: {seed} (replay with {EnvVar.RANDOM_SEED}={seed})"]
    lines += [f"{index}. {item}" for index, item in enumerate(items, 1)]
    return "\n".join(lines)
