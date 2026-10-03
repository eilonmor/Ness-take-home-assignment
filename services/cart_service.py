"""Cart flow: open each item, pick random available variants, add it to the cart."""

from __future__ import annotations

import random
from dataclasses import dataclass

import allure
from playwright.sync_api import Page

from components.variant_selector import VariantChoice
from core.config import Settings
from core.constants import SEED_UPPER_BOUND, AttachmentName, EnvVar, ScreenshotName
from core.exceptions import VariantSelectionError
from core.logger import get_logger
from pages.item_page import ItemPage
from utils.attachments import attach_text


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
        with allure.step(f"Add {len(urls)} items to the cart (variant seed {self.seed})"):
            added = [self._add_item(url, number, len(urls)) for number, url in enumerate(urls, 1)]
        attach_text(_summary(added, self.seed), AttachmentName.CART_ITEMS)
        return added

    def _add_item(self, url: str, number: int, total: int) -> CartItem:
        with allure.step(f"Add item {number}/{total} to the cart: {url}"):
            item = ItemPage(self.page.context.new_page(), self.settings)
            try:
                item.open_listing(url)
                cart_before = item.header.cart_count()
                variants = self._add_with_random_variants(item, url)
                cart_count = item.header.wait_for_cart_count_above(cart_before)
                added = CartItem(url, item.title_text(), item.price_text(), tuple(variants), cart_count)
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

    def _add_with_random_variants(self, item: ItemPage, url: str) -> list[VariantChoice]:
        """Retry with a new random combination while eBay rejects the variants (last error is raised)."""
        attempts = self.settings.cart.variant_attempts
        for attempt in range(1, attempts):
            try:
                return self._select_variants_and_add(item)
            except VariantSelectionError as error:
                self.log.warning("Variant attempt %d/%d failed, trying another combination: %s", attempt, attempts, error)
                item.open_listing(url)  # start again from a page with nothing selected
        return self._select_variants_and_add(item)

    def _select_variants_and_add(self, item: ItemPage) -> list[VariantChoice]:
        variants = item.select_random_variants(self.rng)
        item.keep_quantity_at_one()
        self.log.info("eBay confirmed: %s", item.add_to_cart())
        return variants

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
