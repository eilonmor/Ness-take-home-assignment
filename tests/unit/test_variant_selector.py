"""VariantSelector, checked offline against eBay's variant listbox markup.

The markup is copied from a live item page (2026-10). eBay's script is
replaced by a few lines that do what it does: open the listbox on click,
show the picked value on the button, and drop the sizes that are out of
stock with the picked color.
"""

import random
from collections.abc import Iterator

import pytest
from playwright.sync_api import Page, sync_playwright

from components.variant_selector import VariantChoice, VariantSelector
from core.config import Settings, load_settings
from core.exceptions import VariantSelectionError


def dimension(name: str, *values: str, disabled: tuple[str, ...] = ()) -> str:
    options = "".join(
        f'<div class="listbox__option" role="option" data-sku-value-name="{value}"'
        + (' tabindex="-1" aria-disabled="true"' if value in disabled else "")
        + f'><span class="listbox__value">{value}{" (Out of stock)" if value in disabled else ""} </span></div>'
        for value in values
    )
    return f"""
    <div class="vim x-sku">
      <span class="listbox-button mar-t-16 listbox-button--fluid">
        <button class="listbox-button__control btn btn--form" type="button" aria-haspopup="listbox">
          <span class="btn__cell"><span class="btn__label">{name}:</span><span class="btn__text">Select</span></span>
        </button>
        <div role="listbox" class="listbox__options listbox-button__listbox" hidden>
          <div class="listbox__option listbox__option--active" role="option" aria-selected="true">
            <span class="listbox__value">Select</span>
          </div>
          {options}
        </div>
      </span>
      <div class="error-text" hidden><span>Please select a {name}</span></div>
    </div>"""


EBAY_LISTBOX_SCRIPT = """
<script>{
  // Sizes that have no stock in a given color.
  const outOfStock = { Red: ['S', 'M'] };
  document.querySelectorAll('.x-sku').forEach((sku) => {
    const listbox = sku.querySelector('[role=listbox]');
    sku.querySelector('button').addEventListener('click', () => { listbox.hidden = !listbox.hidden; });
    listbox.addEventListener('click', (event) => {
      const option = event.target.closest('[data-sku-value-name]:not([aria-disabled=true])');
      if (!option) return;
      const value = option.dataset.skuValueName;
      sku.querySelector('.btn__text').textContent = value + ' ';
      listbox.hidden = true;
      (outOfStock[value] || []).forEach((size) =>
        document.querySelectorAll('[data-sku-value-name="' + size + '"]').forEach((o) => o.remove()));
    });
  });
}</script>
"""


def variants_html(*dimensions: str) -> str:
    return f'<div class="vim x-msku-evo" data-testid="x-msku-evo">{"".join(dimensions)}</div>{EBAY_LISTBOX_SCRIPT}'


@pytest.fixture(scope="module")
def settings() -> Settings:
    return load_settings("ci")


@pytest.fixture(scope="module")
def page() -> Iterator[Page]:
    # Local HTML only: no eBay traffic, so headless is fine here.
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_default_timeout(2000)
        yield page
        browser.close()


@pytest.fixture
def selector(page: Page, settings: Settings) -> VariantSelector:
    return VariantSelector(page, settings)


def test_page_without_variants(page: Page, selector: VariantSelector) -> None:
    page.set_content("<div>Plain listing</div>")

    assert not selector.has_variants()
    assert selector.select_random(random.Random(0)) == []


@pytest.mark.parametrize("seed", range(10))
def test_never_picks_an_out_of_stock_value(page: Page, selector: VariantSelector, seed: int) -> None:
    page.set_content(variants_html(dimension("Version", "iPhone 15", "iPhone 15 Pro", disabled=("iPhone 15",))))

    assert selector.select_random(random.Random(seed)) == [VariantChoice("Version", "iPhone 15 Pro")]


@pytest.mark.parametrize("seed", range(10))
def test_reads_each_dimension_after_the_previous_pick(page: Page, selector: VariantSelector, seed: int) -> None:
    # Only Red is in stock; picking it removes sizes S and M, leaving L.
    page.set_content(
        variants_html(
            dimension("Color", "Blue", "Red", disabled=("Blue",)),
            dimension("Size", "S", "M", "L"),
        )
    )

    choices = selector.select_random(random.Random(seed))

    assert choices == [VariantChoice("Color", "Red"), VariantChoice("Size", "L")]
    assert [text.strip() for text in page.locator(".btn__text").all_inner_texts()] == ["Red", "L"]


def test_same_seed_gives_the_same_choices(page: Page, selector: VariantSelector) -> None:
    html = variants_html(dimension("Color", "Black", "White", "Green"), dimension("Size", "XL", "XXL", "3XL"))
    picks = []
    for _ in range(2):
        page.set_content(html)
        picks.append(selector.select_random(random.Random(42)))

    assert picks[0] == picks[1]


def test_dimension_with_nothing_in_stock_fails_clearly(page: Page, selector: VariantSelector) -> None:
    page.set_content(variants_html(dimension("Size", "7", "8", disabled=("7", "8"))))

    with pytest.raises(VariantSelectionError, match="No available value for 'Size'"):
        selector.select_random(random.Random(0))


def test_missing_values_lists_the_flagged_dimensions(page: Page, selector: VariantSelector) -> None:
    page.set_content(variants_html(dimension("Color", "Black"), dimension("Size", "M")))
    page.locator(".x-sku").nth(1).locator(".error-text").evaluate("node => node.hidden = false")

    assert selector.missing_values() == ["Size"]
