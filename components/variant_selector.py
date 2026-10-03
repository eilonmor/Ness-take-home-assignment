"""Variation pickers (Size, Color, ...) in the buy box of an item page."""

from __future__ import annotations

import random
from dataclasses import dataclass

from playwright.sync_api import Locator, Page, expect

from core.base_page import BasePage
from core.config import Settings
from core.exceptions import VariantSelectionError

# Every value of a dimension, except the "Select" placeholder; out-of-stock
# values are rendered as aria-disabled="true", e.g. "iPhone 15 (Out of stock)".
OPTIONS = "[role='option'][data-sku-value-name]"
AVAILABLE_OPTIONS = f"{OPTIONS}:not([aria-disabled='true'])"


@dataclass(frozen=True)
class VariantChoice:
    name: str  # "Size"
    value: str  # "10.5"

    def __str__(self) -> str:
        return f"{self.name}: {self.value}"


class VariantSelector(BasePage):
    """One eBay ``listbox-button`` per dimension, inside ``[data-testid=x-msku-evo]``.

    Picking a value in one dimension removes the values of the other dimensions
    that have no stock with it (pick Color "Cardinal" and sizes XS and 4XL go
    away). So dimensions are picked in page order, and each one's options are
    read only after the previous pick: every combination chosen this way is in stock.
    """

    def __init__(self, page: Page, settings: Settings) -> None:
        super().__init__(page, settings)
        self.root = page.locator("[data-testid='x-msku-evo']")
        self.dimensions = self.root.locator(".x-sku")
        # Shown under a dimension when "Add to cart" is clicked without a value.
        self.missing_value_errors = self.dimensions.locator(".error-text:not([hidden])")

    def has_variants(self) -> bool:
        return self.dimensions.count() > 0

    def select_random(self, rng: random.Random) -> list[VariantChoice]:
        """Pick a random available value in every dimension; returns what was picked."""
        return [self._select_random_value(self.dimensions.nth(index), rng) for index in range(self.dimensions.count())]

    def missing_values(self) -> list[str]:
        """Names of the dimensions eBay flags as not selected."""
        return [
            self._name(dimension)
            for dimension in self.dimensions.all()
            if dimension.locator(".error-text:not([hidden])").count()
        ]

    def _select_random_value(self, dimension: Locator, rng: random.Random) -> VariantChoice:
        name = self._name(dimension)
        available = dimension.locator(AVAILABLE_OPTIONS)
        values: list[str] = available.evaluate_all(
            "options => options.map(o => o.getAttribute('data-sku-value-name').trim())"
        )
        if not values:
            raise VariantSelectionError(
                f"No available value for '{name}' (all out of stock with the values picked so far)"
            )

        index = rng.randrange(len(values))
        self.log.info("%s: picking %r out of %d available %s", name, values[index], len(values), values)
        self.click(dimension.locator("button.listbox-button__control"))
        self.click(available.nth(index))
        expect(dimension.locator(".btn__text")).to_have_text(values[index])
        return VariantChoice(name, values[index])

    @staticmethod
    def _name(dimension: Locator) -> str:
        return dimension.locator(".btn__label").inner_text().strip().rstrip(":")
