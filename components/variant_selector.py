"""Variation pickers (Size, Color, ...) in the buy box of an item page."""

from __future__ import annotations

import random
from dataclasses import dataclass

from playwright.sync_api import Locator, Page, expect

from core.base_page import BasePage
from core.config import Settings
from core.constants import VariantSelectorLocators as Locators
from core.exceptions import VariantSelectionError


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
        self.root = page.locator(Locators.ROOT)
        self.dimensions = self.root.locator(Locators.DIMENSION)
        self.missing_value_errors = self.dimensions.locator(Locators.MISSING_VALUE_ERROR)

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
            if dimension.locator(Locators.MISSING_VALUE_ERROR).count()
        ]

    def _select_random_value(self, dimension: Locator, rng: random.Random) -> VariantChoice:
        name = self._name(dimension)
        available = dimension.locator(Locators.AVAILABLE_OPTIONS)
        values: list[str] = available.evaluate_all(
            "(options, attribute) => options.map(o => o.getAttribute(attribute).trim())",
            Locators.VALUE_NAME_ATTRIBUTE,
        )
        if not values:
            raise VariantSelectionError(
                f"No available value for '{name}' (all out of stock with the values picked so far)"
            )

        index = rng.randrange(len(values))
        self.log.info("%s: picking %r out of %d available %s", name, values[index], len(values), values)
        self.click(dimension.locator(Locators.DROPDOWN_BUTTON))
        self.click(available.nth(index))
        expect(dimension.locator(Locators.SELECTED_VALUE)).to_have_text(values[index])
        return VariantChoice(name, values[index])

    @staticmethod
    def _name(dimension: Locator) -> str:
        return dimension.locator(Locators.DIMENSION_LABEL).inner_text().strip().rstrip(":")
