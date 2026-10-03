"""Every fixed value the framework relies on, in one place.

Grouped by the module that uses it. Values that change per run (base URL,
headless, timeouts, data file, ...) are *not* here: they live in the YAML
profiles under ``config/`` and reach the code through ``core.config.Settings``.
What is here is fixed by eBay's markup and URLs, by the spec, or by the
framework's own conventions.

Locators are CSS unless the group says XPath. The classes are namespaces,
never instantiated. Templates with ``{placeholders}`` are filled with
``str.format``.
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path


def _has_class(name: str) -> str:
    """XPath test for one whole class token (``contains(@class, 's-card')`` would also match 's-card__title')."""
    return f"contains(concat(' ', normalize-space(@class), ' '), ' {name} ')"


# --- Project layout and settings (core/config.py) ---------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROFILES_DIR = PROJECT_ROOT / "config"
DOTENV_FILE = PROJECT_ROOT / ".env"
PROFILE_SUFFIX = ".yaml"
BASE_PROFILE = "base"
DEFAULT_ENV = "dev"


class BrowserName(StrEnum):
    CHROMIUM = "chromium"
    FIREFOX = "firefox"
    WEBKIT = "webkit"


class TraceMode(StrEnum):
    ON = "on"
    OFF = "off"
    RETAIN_ON_FAILURE = "retain-on-failure"


class CartTotalLine(StrEnum):
    """Which order-summary row the cart budget check reads (``cart.total_line``)."""

    # "Items (n)": the item prices only, like the search price filter.
    ITEMS = "items"
    # "Subtotal": items plus shipping, when eBay can quote shipping.
    SUBTOTAL = "subtotal"


BROWSERS = tuple(browser.value for browser in BrowserName)
TRACE_MODES = tuple(mode.value for mode in TraceMode)
CART_TOTAL_LINES = tuple(line.value for line in CartTotalLine)
TRUE_VALUES = ("1", "true", "yes", "on")
FALSE_VALUES = ("0", "false", "no", "off")


class EnvVar:
    """Environment variables read by ``core.config`` (also from ``.env``)."""

    ENV = "ENV"
    BASE_URL = "BASE_URL"
    BROWSER = "BROWSER"
    HEADLESS = "HEADLESS"
    SLOW_MO = "SLOW_MO"
    GUEST = "EBAY_GUEST"
    RANDOM_SEED = "RANDOM_SEED"
    TRACE = "TRACE"
    STEALTH = "STEALTH"
    BROWSER_CHANNEL = "BROWSER_CHANNEL"
    USERNAME = "EBAY_USERNAME"
    PASSWORD = "EBAY_PASSWORD"


class ArtifactFiles:
    """Layout and names of the files written under ``artifacts.dir`` (reports/)."""

    SCREENSHOTS_DIR = "screenshots"
    TRACES_DIR = "traces"
    LOGS_DIR = "logs"
    SCREENSHOT_SUFFIX = ".png"
    TRACE_SUFFIX = ".zip"
    # Allure wants the extension without the dot.
    TRACE_ATTACHMENT_EXTENSION = "zip"
    FAILURE_SCREENSHOT = "{run_id}_failure_{index}"
    # Read by Allure for the report's "Environment" widget.
    ALLURE_ENVIRONMENT = "environment.properties"


# --- Logging, files, data (core/logger.py, utils/files.py, core/data_loader.py)


class Logging:
    ROOT_LOGGER = "ness"
    FORMAT = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
    FILE_NAME = "run.log"
    DEFAULT_LEVEL = "INFO"


class Files:
    MAX_NAME_LENGTH = 100
    FALLBACK_NAME = "unnamed"
    # Microseconds; utils.files.timestamp trims them to milliseconds.
    TIMESTAMP_FORMAT = "%Y%m%d-%H%M%S-%f"


# Spec 5.2: search_items_by_name_under_price(query, max_price, limit=5).
DEFAULT_SEARCH_LIMIT = 5
SEARCH_CASES_KEY = "cases"


# --- Waits and actions (core/base_page.py) ----------------------------------


class Waits:
    # BasePage.is_visible: how long to wait for an element that may never come (popups, filters).
    OPTIONAL_ELEMENT_TIMEOUT_MS = 2000
    # BasePage.click: extra attempts after e.g. an overlay intercepted the first click.
    CLICK_RETRIES = 1
    NAVIGATION_WAIT_UNTIL = "domcontentloaded"
    # Before "Add to cart": clicked earlier, the link navigates away instead of opening the dialog.
    PAGE_SCRIPTS_READY = "load"


# --- eBay URLs ----------------------------------------------------------------


class Endpoints:
    """Paths relative to ``Settings.base_url`` (the base URL itself is in config/base.yaml)."""

    HOME = "/"
    SEARCH = "/sch/i.html"
    # URL fragments that identify a page type.
    SEARCH_PATH_PART = "/sch/"
    ITEM_PATH_PART = "/itm/"


class QueryParam:
    KEYWORDS = "_nkw"
    MAX_PRICE = "_udhi"
    PAGE = "_pgn"
    RESULTS_TYPE = "rt"


# rt=nc: eBay's own value when it applies a filter through the URL.
RESULTS_TYPE_NO_CACHE = "nc"
FIRST_PAGE = 1

SIGN_IN_HOST_PART = "signin.ebay."
# The "Add to cart" link points here; it is followed only when the click lands
# before the page's scripts take it over (then eBay shows the cart page instead
# of the dialog, but the item is added all the same).
CART_URL_PARTS = ("cart.ebay.", "cart.payments.ebay.")


class BotChallenge:
    """eBay answers suspected bots with one of these pages instead of the content.

    "Error Page" is what a headless browser gets on a cold visit.
    """

    TITLES = ("Pardon Our Interruption", "Security Measure", "Error Page")
    URL_PARTS = ("/splashui/captcha", "/splashui/challenge")


# --- Locators: components --------------------------------------------------

_LIGHTBOX_CLOSE_BUTTON = "button.lightbox-dialog__close"


class HeaderLocators:
    """CSS, not role locators: while the ship-to dialog is open eBay marks the
    rest of the header ``aria-hidden``, so role locators find nothing."""

    ROOT = "#gh"
    IDENTITY = ".gh-identity"
    # Guest: <span class="gh-identity-signed-out-unrecognized">Hi! <a>Sign in</a> or <a>register</a>
    SIGNED_OUT_MARKER = "[class*='signed-out']"
    SIGN_IN_LINK = f"a[href*='{SIGN_IN_HOST_PART}']"
    SHIP_TO_DIALOG = ".address-dialog__lightbox"
    SHIP_TO_DISMISS = _LIGHTBOX_CLOSE_BUTTON
    SEARCH_INPUT = "#gh-ac"
    SEARCH_BUTTON = "#gh-search-btn"
    # Number of items in the cart; not rendered while the cart is empty.
    CART_BADGE = ".gh-cart .gh-badge"
    # Not a[href*='cart.ebay']: the sign-in links carry the cart URL in their ?ru= param.
    CART_LINK = ".gh-cart a.gh-flyout__target"


class AddedToCartDialogLocators:
    ROOT = ".x-atc-action__overlay"
    # Only rendered once the item is in the cart (the spinner state has no details).
    DETAILS = ".x-atc-layer-v3--info"
    CLOSE_BUTTON = _LIGHTBOX_CLOSE_BUTTON


class PaginationLocators:
    # On the last page "next" is missing or rendered disabled, without a link.
    NEXT_LINK = "nav.pagination a.pagination__next[href]:not([aria-disabled='true'])"


class PriceFilterLocators:
    SECTION = ".su-price-filter__section"
    # The placeholder names the currency ("Max ILS", "Max $"), so match the prefix only.
    MAX_INPUT = "input[placeholder^='Max']"
    SUBMIT_BUTTON = "button.su-textrange__submit-button"


class VariantSelectorLocators:
    ROOT = "[data-testid='x-msku-evo']"
    DIMENSION = ".x-sku"
    # Shown under a dimension when "Add to cart" is clicked without a value.
    MISSING_VALUE_ERROR = ".error-text:not([hidden])"
    VALUE_NAME_ATTRIBUTE = "data-sku-value-name"
    # Every value of a dimension, except the "Select" placeholder; out-of-stock
    # values are rendered as aria-disabled="true", e.g. "iPhone 15 (Out of stock)".
    OPTIONS = f"[role='option'][{VALUE_NAME_ATTRIBUTE}]"
    AVAILABLE_OPTIONS = f"{OPTIONS}:not([aria-disabled='true'])"
    DROPDOWN_BUTTON = "button.listbox-button__control"
    SELECTED_VALUE = ".btn__text"
    DIMENSION_LABEL = ".btn__label"


# --- Locators: pages ----------------------------------------------------------


class ItemPageLocators:
    TITLE = "h1.x-item-title__mainTitle"
    PRICE = "[data-testid='x-price-primary']"
    QUANTITY_INPUT = "[data-testid='x-quantity'] input[name='quantity']"
    ADD_TO_CART_BUTTON = "[data-testid='x-atc-action'] a.ux-call-to-action"


class ItemPageValues:
    # One unit per item, so the cart total stays comparable to budget * item count.
    QUANTITY = "1"
    PRICE_NOT_SHOWN = "n/a"
    CART_PAGE_OPENED = "Opened the cart page"


class CartPageLocators:
    """cart.ebay.com. eBay's own ``data-test-id`` hooks, not its layout classes."""

    SUMMARY = "[data-test-id='cart-summary']"
    # Order summary rows, in the currency the search shows (e.g. "ILS 210.70").
    # "Item (1)" / "Items (3)": sum of the item prices.
    ITEM_TOTAL = "[data-test-id='ITEM_TOTAL']"
    SUBTOTAL = "[data-test-id='SUBTOTAL']"
    # One per listing, grouped by seller (cart-bucket).
    LINE_ITEM = "[data-test-id='cart-bucket'] [data-test-id='list-summary']"
    LINE_TITLE = "[data-test-id='cart-item-link']"
    # Relative to a line. The listing's currency first, then the converted price:
    # "US $68.99 (ILS 210.70)". The summary rows use the converted one.
    LINE_PRICE = ".price-details"
    LINE_QUANTITY = ".quantity input"


class LoginPageLocators:
    USERNAME_INPUT = "#userid"
    CONTINUE_BUTTON = "#signin-continue-btn"
    PASSWORD_INPUT = "#pass"
    SIGN_IN_BUTTON = "#sgnBt"
    # Inline error under the field, e.g. "We couldn't find this eBay account."
    ERROR_MESSAGE = "#signin-error-msg"


class SearchResultsXPaths:
    """XPath locators for the results page (spec 5.2)."""

    PREFIX = "xpath="
    # Site texts and classes the card filters below key on.
    PLACEHOLDER_CARD_TITLE = "Shop on eBay"
    FEWER_WORDS_DIVIDER = "srp-river-answer--REWRITE_START"
    BUY_IT_NOW = "Buy It Now"
    BIDS = " bid"

    RESULTS_LIST = f"//ul[{_has_class('srp-results')}]"
    # Real listings only. Skipped: carousels / filter / paging rows (srp-river-answer),
    # the "Shop on eBay" placeholder card, and everything after the "Results matching
    # fewer words" divider (those cards do not match the query).
    ITEM_CARDS = (
        f"{RESULTS_LIST}/li[{_has_class('s-card')}][@data-listingid]"
        f"[not(starts-with(normalize-space(.//*[contains(@class, 's-card__title')]), '{PLACEHOLDER_CARD_TITLE}'))]"
        f"[not(preceding-sibling::li[contains(@class, '{FEWER_WORDS_DIVIDER}')])]"
    )
    NO_RESULTS = "//*[contains(@class, 'srp-save-null-search')]"
    # Relative to a card; the keys are read by the card reader script in pages/search_results_page.py.
    CARD_FIELDS = {
        # The title also holds a visually hidden "Opens in a new window or tab" span.
        "title": ".//*[contains(@class, 's-card__title')]/span[not(contains(@class, 'clipped'))]",
        "link": f".//a[contains(@class, 's-card__link')][contains(@href, '{Endpoints.ITEM_PATH_PART}')]",
        # One row per price: a range is three spans in one row ("$1" " to " "$2");
        # an auction with Buy It Now has a bid row and a Buy It Now row. The crossed-out
        # "was" price sits in the same row with another class, so it is not selected.
        "price_rows": f".//div[{_has_class('s-card__attribute-row')}][span[contains(@class, 's-card__price')]]",
        "price_parts": "./span[contains(@class, 's-card__price')]",
        "bids": f".//div[{_has_class('s-card__attribute-row')}]/span[contains(., '{BIDS}')]",
        "buy_it_now": f".//div[{_has_class('s-card__attribute-row')}]/span[normalize-space() = '{BUY_IT_NOW}']",
    }


# --- Prices (utils/price_parser.py) -----------------------------------------

# Longest first: "US $" must win over "$".
CURRENCY_SYMBOLS = (
    ("US $", "USD"),
    ("C $", "CAD"),
    ("AU $", "AUD"),
    ("$", "USD"),
    ("£", "GBP"),
    ("€", "EUR"),
    ("₪", "ILS"),
)
FREE_PRICE_WORD = "free"


# --- Cart (services/cart_service.py) ----------------------------------------

# A fresh variant seed is drawn from [0, SEED_UPPER_BOUND) when none is configured.
SEED_UPPER_BOUND = 2**32


# --- Report evidence: screenshot and Allure attachment names ----------------


class ScreenshotName:
    BOT_CHALLENGE = "bot_challenge"
    SESSION_READY = "session_ready_{label}"
    SEARCH_PAGE = "search_{query}_page_{page}"
    CART_ITEM = "cart_item_{number}"
    CART_ITEM_FAILED = "cart_item_{number}_failed"
    CART_PAGE = "cart_page"


class AttachmentName:
    TRACE = "Playwright trace"
    FAILURE_SCREENSHOT = "Failure screenshot (page {index})"
    SEARCH_ITEMS = "Items found for '{query}' (<= {max_price:g})"
    CART_ITEMS = "Items added to the cart"
    CART_CHECK = "Cart total vs. budget"


class HtmlReport:
    TITLE = "Ness eBay E2E report"
    # pytest-html stores --html under this option name.
    PATH_OPTION = "htmlpath"


class AllureFeature:
    SEARCH = "Search"
    CART = "Cart"
    SCENARIO = "Full scenario"


class AllureTitle:
    # Formatted by allure-pytest with the test's parameters.
    CART_BUDGET = (
        "Search '{search_case.query}' <= {search_case.max_price:g}, add to cart, "
        "cart total <= {search_case.budget:g} per item"
    )


class ScenarioStep:
    """Top-level Allure steps of the full scenario (spec 5.5); the services add the detail inside."""

    SEARCH = "1. Search items under the price (spec 5.2)"
    ADD_TO_CART = "2. Add {count} items to the cart (spec 5.3)"
    ASSERT_TOTAL = "3. Assert the cart total is within the budget (spec 5.4)"


# --- Tests: pytest wiring, expected values, assertion messages ---------------


class PytestOption:
    ENV = "--env"
    # A test with this argument runs once per row of the profile's data file.
    SEARCH_CASE_ARG = "search_case"


class Expected:
    # Matched case-insensitively against the home page title.
    HOME_TITLE = "ebay"
    ITEM_URL_PART = Endpoints.ITEM_PATH_PART


class AssertMessage:
    NO_ITEMS_FOUND = "No items found for {query!r} <= {max_price:g}"
    DUPLICATE_URLS = "Duplicate URLs: {urls}"
    PRICE_ABOVE_MAX = "{title!r} costs {price}, above {max_price:g}"
    CART_COUNT = "Cart shows {actual} items, expected {expected}"
    NOT_BACK_ON_SEARCH = "Expected to be back on the search results tab"
    ITEM_TABS_OPEN = "Item tabs should be closed"
    HEADER_SHOWS = "Header shows: {greeting!r}"
    # Spec 5.4: actual vs. budget, and how the budget was computed.
    CART_TOTAL_ABOVE_BUDGET = (
        "Cart {line} {total} is above the budget {budget:,.2f} "
        "({budget_per_item:g} per item x {items_count} items), over by {excess:,.2f}"
    )
    CART_LINES = "Cart has {actual} lines, expected {expected}"


# --- Browser hardening (core/stealth.py, experimental branch) ----------------


class Stealth:
    """Chromium launch/context tweaks applied when ``browser.stealth`` is on."""

    # Stops Blink from setting navigator.webdriver=true and the related automation hooks.
    LAUNCH_ARGS = ("--disable-blink-features=AutomationControlled",)
    # Playwright adds --enable-automation by default (infobar + automation flag); drop it.
    IGNORE_DEFAULT_ARGS = ("--enable-automation",)
    # Headless Chromium advertises itself in the UA; the real version string stays.
    HEADLESS_UA_TOKEN = "HeadlessChrome"
    HEADED_UA_TOKEN = "Chrome"
    # Belt and braces for navigator.webdriver, in case the launch flag is ignored
    # (e.g. a channel/version that still sets it). Runs before any page script.
    INIT_SCRIPT = """
Object.defineProperty(Navigator.prototype, 'webdriver', { get: () => undefined, configurable: true });
"""
