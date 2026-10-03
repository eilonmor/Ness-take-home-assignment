# Design Decisions

Short records of the main framework choices and the trade-offs behind them.
Format per decision: **Context → Decision → Alternatives → Consequences**.

---

## ADR-1 — Own pytest fixtures instead of `pytest-playwright`

**Context.**
In JavaScript, Playwright Test reads one `playwright.config.ts` file (browser, timeouts, base URL, tracing, projects).
Python has no such file: that config belongs to the JS test runner only.
The Python plugin `pytest-playwright` is driven by **CLI flags** (`--browser`, `--headed`, `--slowmo`, `--tracing`, `--screenshot`), not by environment profiles.
It also has no built-in setting for per-environment action/navigation timeouts or the `expect()` timeout, and it does not attach evidence to Allure.

**Decision.**
Write our own fixtures in [tests/conftest.py](../tests/conftest.py) (`settings → playwright → browser → context → page`).
All values come from the active profile ([ADR-2](#adr-2--yaml-profiles-are-our-playwrightconfigts)).
`pytest-playwright` is removed from the dependencies.

**Alternatives considered.**

| Option | Pros | Cons |
|---|---|---|
| **1. Own fixtures (chosen)** | One source of truth (the profile). Full control of timeouts, `expect` timeout, tracing and Allure attachments. Shows the framework layer explicitly. | About 100 lines to maintain. The plugin's CLI flags are gone. |
| 2. Plugin as-is | Zero code. Familiar flags. Runs across several browsers built in. | Settings are split between CLI flags and our config. No profiles, no Allure attachments. Evidence goes to `test-results/` only. |
| 3. Hybrid: keep the plugin and override `browser_type_launch_args` / `browser_context_args` from the profile | Keeps the flags and the multi-browser runs. | Two sources of truth: CLI flags and the profile can contradict each other, and which one wins is not obvious. Timeouts, Allure and failure handling still need custom code, so most of option 1 is written anyway. |

Option 1 was chosen because configuration and architecture are a large part of the grading, and a single, explicit source of truth is easier to read and to review.

**Consequences.**
- ✅ `ENV=ci pytest` changes browser, timeouts and evidence policy in one place.
- ❌ `--headed`, `--browser` and `--slowmo` no longer exist. Replacements: `HEADLESS=false`, `BROWSER=firefox`, `SLOW_MO=250`.
- ❌ No built-in runs across several browsers in one command. Run once per `BROWSER` instead, or add a `browsers:` list to the profile later.
- ℹ️ Only Chromium is installed by default. For the others: `python -m playwright install firefox webkit`.

---

## ADR-2 — YAML profiles are our `playwright.config.ts`

**Context.** The same tests must run locally (visible browser, slow, verbose logs) and in CI (headless, patient timeouts) without code changes.

**Decision.** Settings live in [config/](../config/) and are loaded into typed, read-only dataclasses by [core/config.py](../core/config.py).
Each layer overrides only the keys it sets (later wins):

```
config/base.yaml  →  config/<ENV>.yaml (dev | ci)  →  env vars: BASE_URL, BROWSER, HEADLESS, SLOW_MO
```

The profile is chosen by `pytest --env ci`, else `ENV=ci` (shell or `.env`), else `dev`.

**Alternatives.** Hard-coded constants (no ENV support). Settings in `pytest.ini` (no nesting, no typing). Environment variables only (hard to read once there are more than a handful).

**Consequences.**
- ✅ A new environment means one small YAML file.
- ✅ Invalid values (unknown profile, browser or trace mode) stop the run at startup with a clear message. This is covered by unit tests.
- ❌ One more place to look, compared with constants. The order of the layers is written down here and in the module docstring.

---

## ADR-3 — One browser per session, a fresh context per test

**Context.** Each scenario changes server-side state through cookies (the guest cart). Starting a browser process is slow (about 1 s); creating a context is cheap (a few ms).

**Decision.** `browser` is session-scoped; `context` and `page` are created per test.

**Alternatives.** A new browser per test is fully isolated but slow. A shared context per session is fast, but carts and cookies leak between tests, which causes order-dependent failures.

**Consequences.**
- ✅ Every test starts with an empty cart and its own cookies, so tests can run in any order.
- ✅ Tracing and failure evidence are per test.
- ❌ No session reuse: each test is a new guest. That fits the guest-login approach.

---

## ADR-4 — Failure evidence: trace + screenshots, attached to Allure

**Context.** Tests against a live site (eBay) fail for reasons that are hard to reproduce: pop-ups, A/B layouts, bot checks. A stack trace alone is not enough.

**Decision.**
- Trace mode defaults to `retain-on-failure`: tracing always runs, and the zip is kept only when the test fails. It can be `on` or `off` per profile.
- On failure, a **full-page screenshot of every open page** is taken. This covers items opened in new tabs.
- Files are saved under `reports/screenshots/` and `reports/traces/`, and are **attached to Allure**. They appear in the test's **Tear down** section, because they are captured in fixture teardown.
- Pages can also save step screenshots through `BasePage.take_screenshot()`, which are attached inline.

**Alternatives.** Always keep traces: slow, and gigabytes of data on green runs. Screenshot only the current page: misses the tab that actually failed. Evidence only on disk: reviewers of the report cannot see it.

**Consequences.**
- ✅ A red test in Allure carries everything needed to debug it. Open the trace with `playwright show-trace <file>.zip`.
- ❌ Tracing has a small overhead even on passing tests (screenshots + DOM snapshots are recorded, then discarded).

---

## ADR-5 — Test data in YAML, expanded by `pytest_generate_tests`

**Context.** Milestone 2: adding a scenario must not need code changes. The rows also need validating: a typo such as `max_pirce` or `limit: yes` must not quietly turn into a wrong test against a live site.

**Decision.**
- Scenarios live in [data/search_cases.yaml](../data/search_cases.yaml) under `cases:`. The file path comes from the profile (`data.search_cases`), so a profile can point to a smaller or bigger data set.
- [core/data_loader.py](../core/data_loader.py) turns each row into a frozen `SearchCase`. It rejects unknown keys, wrong types, non-positive numbers, empty files and duplicate ids, and the error names the file and row number. `.json` files work too (`yaml.safe_load` reads JSON).
- A `pytest_generate_tests` hook in [tests/conftest.py](../tests/conftest.py) parametrizes **any** test that takes a `search_case` argument, with the row `id` as the test id (e.g. `[shoes-under-220]`).
- Login: `auth.guest` (default `true`) is set in the profile and can be overridden by `EBAY_GUEST`. `EBAY_USERNAME` / `EBAY_PASSWORD` are read **only** from the environment or `.env` (git-ignored; template in [.env.example](../.env.example)). `EBAY_GUEST=false` without both credentials stops the run at startup. The password is kept out of `repr`, so it never shows up in logs.

**Alternatives.**

| Option | Why not |
|---|---|
| `@pytest.mark.parametrize("case", load_cases())` on each test | The file is read at import time, every test repeats the decorator, and the profile (`--env`) is not known yet at import. |
| Plain dicts instead of a dataclass | No validation or typing; a typo surfaces deep inside a page object. |
| CSV | Flat only. Optional fields and comments are clumsy. |

**Consequences.**
- ✅ A new row means a new test case, with its own id in pytest, Allure and the artifact file names.
- ✅ Bad data fails at collection with a precise message instead of halfway through a browser session.
- ❌ The settings are now loaded at collection time too, so an invalid profile or `.env` also breaks `pytest --collect-only`. They are loaded once and cached on `config.stash`, so the fixtures reuse the same instance.

---

## ADR-6 — Guest session by default, behind an `AuthService`

**Context.** The spec requires a login step but allows a guest/stub one. Probing eBay showed:
- A headless browser gets `Error Page | eBay` on the home page and is redirected to `/splashui/captcha` ("Security Measure") on sign-in.
- Headed runs reach the sign-in form (`#userid` → `#signin-continue-btn` → `#pass` → `#sgnBt`), but a burst of runs is rate-limited with the same block pages.
- A guest can search and use the cart, which is all the scenario needs.
- An "Are you shipping to …?" modal opens on first visit and intercepts every click until it is dismissed.

**Decision.**
- [services/auth_service.py](../services/auth_service.py) `AuthService.start_session()` opens the home page and returns a `UserSession`. With `auth.guest: true` (the default) it checks that the header shows the signed-out state. With `EBAY_GUEST=false` it signs in through [pages/login_page.py](../pages/login_page.py) and checks that the header shows a signed-in user.
- Tests ask for the `user_session` fixture. The scenario code does not know or care which mode is active.
- [components/header.py](../components/header.py) closes the ship-to modal and reads the sign-in state with CSS locators. While the modal is open, eBay marks the rest of the header `aria-hidden`, so role locators find nothing.
- `BasePage.open()` checks for bot-check pages and raises `BotChallengeError` with a screenshot. `LoginPage` turns inline errors ("We couldn't find this eBay account") and unexpected extra steps (2FA, passkey) into `LoginError`.

**Alternatives.**

| Option | Why not |
|---|---|
| Always sign in | Captcha cannot be automated reliably (or legitimately), so every run would depend on a human. |
| Reuse a saved `storage_state` from a manual login | Works, but the session cookies are credentials: they must not be committed and they expire. It is a possible extension, with the file path in `.env`. |
| Bypass bot detection (patched user agent, stealth plugins) | Works against the site's protection on purpose. Running headed and documenting the limitation is the honest choice. |

**Consequences.**
- ✅ The scenario runs without an account. Switching to a real sign-in is a `.env` change, not a code change.
- ✅ A blocked run fails in about 2 s with "eBay served a bot check (title 'Error Page | eBay')…" instead of a timeout on a missing element.
- ✅ The password never reaches a trace. A trace stores every `fill()` value in plain text, and failing traces are attached to the report. So the password step runs inside `tracing_paused` ([utils/tracing.py](../utils/tracing.py)), and [tests/unit/test_tracing.py](../tests/unit/test_tracing.py) checks the trace zip for the secret. *Corrected in ADR-13:* the first version paused with `stop_chunk()`, which still kept the password in the network log of the form POST.
- ❌ A trace of a real-login run starts after sign-in: the home page and the sign-in steps are dropped. A failed sign-in is still covered by the failure screenshot and the `LoginError` message.
- ❌ Real sign-in is implemented but not verified end to end (no test account, and headless always hits the captcha). Only the unknown-account error path was checked by hand. *Update:* there is now a test account, and ADR-13 adds live tests for the sign-in form.
- ❌ Guest only: no saved addresses or watchlist. Prices and the cart total are those shown to an anonymous visitor in the detected region.

---

## ADR-7 — Search: UI price filter first, every card checked by XPath, paging with a cap

**Context.** Spec 5.2 asks for the first `limit` items priced ≤ `max_price`, collected with XPath, using the site's price filter when there is one and paging when needed. Probing the live results page (2026-10) showed:
- Cards are `ul.srp-results > li.s-card[data-listingid]`. The same list also holds carousels, "Popular Filters" and the pager (`li.srp-river-answer--*`), and may have a "Shop on eBay" placeholder and a "Results matching fewer words" divider.
- A card has one `s-card__attribute-row` per price. A range is three `s-card__price` spans ("ILS 81.50", " to ", "ILS 110.86"). A sale shows a crossed-out "was" price in the same row, with a different class. An auction can show a bid row **and** a Buy It Now row.
- The price filter box takes whole numbers only, and eBay navigates to `…&_udhi=<max>` a moment *after* the click.
- Prices are shown in the visitor's currency (ILS from Israel), not the profile's `currency: USD`. The filter works in the displayed currency.
- A cold `page.goto()` to a `/sch/...` URL is answered with "Pardon Our Interruption"; searching through the header box is not.

**Decision.**
- Flow in [services/search_service.py](../services/search_service.py): `Header.search(query)` → `SearchResultsPage.apply_max_price()` → read cards → next page, until `limit`, no next page, or `search.max_pages` (profile, default 5).
- The filter is applied through the sidebar box ([components/price_filter.py](../components/price_filter.py)), rounded **up** to a whole number so no matching item is filtered out. Setting `_udhi` in the URL is only the fallback when the box is missing.
- The filter only narrows the results. Every card is still checked: `price.high <= max_price`, using the **upper** bound of a range and the **highest** price on the card (the Buy It Now price of an auction). Auction-only cards are skipped (they cannot go in a cart, Stage 5), as are cards without a readable price and URLs already collected.
- All card fields are read with the XPaths in [pages/search_results_page.py](../pages/search_results_page.py), evaluated in the page in **one** `evaluate_all` call per page.
- Item URLs are returned without the query string (`https://www.ebay.com/itm/<id>`), which also makes duplicates across pages easy to spot.
- `max_price` is compared in the currency eBay displays. A mismatch with the profile currency is logged as a warning, not treated as an error.
- Click-started navigations are wrapped in `BasePage.expect_navigation()`. It waits for the navigation that the click starts, not just for a matching URL (a second search from a results page already matches `/sch/`). A bot-check redirect also ends the wait and raises `BotChallengeError`.

**Alternatives.**

| Option | Why not |
|---|---|
| Build the search URL (`/sch/i.html?_nkw=…&_udhi=…`) and `goto` it | Fastest, but a cold deep link gets the bot page. |
| Trust the filter and take the first `limit` cards | The filter compares the *current bid* of an auction and the *lower* bound of a range, so items above the max get through. |
| One locator call per field per card | Many round trips per page, each slowed by `slow_mo`, and the DOM can change between them. |
| Convert prices to the profile currency | Needs live exchange rates; the cart total (Stage 6) is shown in the same displayed currency anyway. |
| Skip sponsored cards | Sponsored cards are real listings that match the query and price. The new layout hides the "Sponsored" label behind obfuscated markup, so detection would be guesswork. |

**Consequences.**
- ✅ Every returned item is verified against `max_price` on the page itself, whatever the filter did.
- ✅ The XPaths and the price logic are covered offline: [tests/unit/test_search_results_page.py](../tests/unit/test_search_results_page.py) runs them in a local headless browser against markup copied from a live page, and [tests/unit/test_price_parser.py](../tests/unit/test_price_parser.py) covers the parser.
- ❌ The locators target eBay's current `s-card` layout. The older `s-item` layout, which eBay may still serve in some A/B buckets, is not supported. All selectors are constants in one module, so a layout change is a local edit.
- ❌ `max_price: 220` means 220 in whatever currency the visitor sees. Running from another country changes the meaning of the data rows. This is documented in the README.
- ❌ Shipping is not part of the price check (the spec compares the item price).
- *Update (2026-10):* on a "0 results" page eBay still fills the list with fuzzy matches on parts of the query (seen live: 14 bulbs and RAM sticks for "qzxvkj wplmnr 9h7t3"), with no "fewer words" divider before them. `ITEM_CARDS` now also skips every card after the "No exact matches found" block (`srp-save-null-search`). Before this fix, a search with no matches returned unrelated items.

---

## ADR-8 — Add to cart: one tab per item, variants picked in order from a seeded RNG

**Context.** Spec 5.3 asks to open each URL, pick random **available** variant values, click "Add to cart", go back to the search, and save a screenshot and log per item. Probing live item pages (2026-10) showed:
- Variants are eBay's custom `listbox-button` widgets, one `.x-sku` per dimension inside `[data-testid=x-msku-evo]`, not native `<select>`s. Values are `[role=option][data-sku-value-name]`. Out-of-stock values stay in the list with `aria-disabled="true"` and "(Out of stock)" in the text.
- Dimensions depend on each other: picking Color "Heather Cardinal" **removes** sizes XS and 4XL from the Size list.
- "Add to cart" (`[data-testid=x-atc-action] a`) opens an in-page overlay: a spinner, then "Added to cart" with the item details. The page URL does not change. The link's `href` is a real `cart.payments.ebay.com/sc/add?...` URL, followed when the click lands before the page's scripts take over.
- Clicking "Add to cart" with a dimension unselected adds nothing and shows "Please select a Size" (`.error-text`) under it.
- The header cart badge (`.gh-cart .gh-badge`) updates in place after an add.
- The quantity box is disabled when only one unit is for sale ("Last one").

**Decision.**
- Flow in [services/cart_service.py](../services/cart_service.py): for each URL, open a **new tab** in the same context → `ItemPage.open_listing()` → `select_random_variants()` → `keep_quantity_at_one()` → `add_to_cart()` → wait for the cart badge to go up → screenshot (with the "Added to cart" overlay showing) + log → close the tab and bring the search tab to the front. That is "go back to the search tab": the results page was never left.
- [components/variant_selector.py](../components/variant_selector.py) picks dimensions **in page order** and reads a dimension's available options only after the previous pick, so each pick sees what eBay left in stock for the values chosen so far. Disabled values are never candidates.
- Randomness comes from `random.Random(seed)`. The seed is `cart.random_seed` in the profile / `RANDOM_SEED`, or a fresh random one, and is always logged and attached to the report, so a failing combination can be replayed.
- Quantity stays at **1**. The spec mentions quantity among the variants, but Stage 6 checks `total <= budget_per_item * items_count`; a random quantity would break that comparison.
- An add counts as done only when eBay confirms it: the overlay details appear **and** the cart badge goes up. A visible "Please select …" error raises `VariantSelectionError`; the page is reloaded and another random combination is tried, up to `cart.variant_attempts` (profile, default 3). Anything else (no "Add to cart" button, no confirmation) raises `AddToCartError` at once. The run stops at the first item that cannot be added, because the cart total check is only meaningful when every item is in.
- Before clicking "Add to cart" the page waits for `load`. If eBay still follows the link to the cart page, that also counts as added. For this reason the item's title and (variant) price are read **before** the click: after it, the tab may no longer be the item page.
- The cart count to beat is read once on the search tab (fully loaded) and then carried from item to item. Reading it in each new item tab could catch the header before the badge renders and report 0.

**Alternatives.**

| Option | Why not |
|---|---|
| Same tab, `page.go_back()` after each item | Variant picks rewrite the URL (`?var=…`), so the number of history steps back to the results is not fixed. The search page would also reload every time, a bigger rate-limit footprint. |
| Click the result card, which opens the item in a new tab | Needs the card on screen for each URL. The spec's input is a URL list (5.3 takes `urls`), which may come from several result pages. |
| Pick all dimensions up front from the initial option lists | Misses the dependency between dimensions: Red + S can be in the list before Red is chosen and gone after. |
| Unseeded `random.choice` | Random failures could not be reproduced. |
| Random quantity | Breaks the budget × item count check of Stage 6; listings with one unit do not allow it anyway. |
| Skip items that cannot be added and go on | The cart check would pass with fewer items than `items_count` and hide the problem. |

**Consequences.**
- ✅ Every item in the cart is confirmed twice (overlay + badge), with a screenshot of the confirmation in the report.
- ✅ The service flow is tested offline with stubbed pages ([tests/unit/test_cart_service.py](../tests/unit/test_cart_service.py)): retries up to `variant_attempts`, no retry for other errors, every item tab closed, cart count carried over.
- ✅ The variant logic is tested offline: [tests/unit/test_variant_selector.py](../tests/unit/test_variant_selector.py) runs it against copied listbox markup, with a small script that mimics eBay's behaviour (open, pick, drop out-of-stock sizes).
- ✅ The search tab is untouched, so the search could go on from where it stopped.
- ❌ Only the `listbox-button` variant widget is supported. Native `<select>` pickers (older layout) and image swatches were not seen on current pages and are not handled; such a listing fails with "eBay asks to select: …".
- ❌ A "See all options" layout was not found on live pages during probing, so it is not handled.
- ❌ One bad listing (ended between search and add, sold out) fails the whole scenario by design.

---

## ADR-9 — Fixed values in one `core/constants.py`, run-time values in the profiles

**Context.** Selectors, URL paths and query parameters, screenshot and attachment names, env var names, default waits and assertion messages were spread as literals across pages, components, services and tests. Some were module constants (`CART_BADGE`, `MAX_PRICE_PARAM`, `CARD_XPATHS`), others inline strings. A change in eBay's markup or a renamed env var meant hunting through several layers.

**Decision.**
- Every value that is **fixed** (set by eBay's markup and URLs, by the spec, or by framework conventions) lives in [core/constants.py](../core/constants.py), grouped by the module that uses it: `HeaderLocators`, `ItemPageLocators`, `SearchResultsXPaths`, `QueryParam`, `Endpoints`, `EnvVar`, `Waits`, `ScreenshotName`, `AssertMessage`, ...
- Groups are plain namespace classes with `UPPER_SNAKE` attributes, so a call site reads `Locators.ADD_TO_CART_BUTTON` without `.value`. Closed sets that are validated (`BrowserName`, `TraceMode`) are `StrEnum`s; they compare equal to the plain strings read from YAML.
- Messages with parameters are `str.format` templates (`AssertMessage.NO_ITEMS_FOUND.format(query=..., max_price=...)`).
- Values that **change per run** stay in the YAML profiles (ADR-2): base URL, timeouts, browser, data file, paging cap.
- The module lives in `core/` (the bottom layer) and imports nothing from the project, so every layer can use it without cycles.

**Alternatives.**

| Option | Why not |
|---|---|
| Keep locators next to each page object | The classic POM layout and fine on its own, but the values were split between module constants, `__init__` bodies and inline strings, and tests, services and config each had their own literals as well. |
| One `Enum` per group | Every use would need `.value`, and Playwright and `str.format` would get enum members rather than strings. |
| Put selectors in YAML too | Selectors are not something a run should change; loading them from data would lose IDE navigation and import-time errors. |
| Use the constants inside unit tests | A unit test that builds its expected value from the same constant cannot catch a wrong constant. Unit tests keep their own literal inputs and expectations. |

**Consequences.**
- ✅ A layout change on eBay is an edit to one group in one file; pages and components only hold structure and behaviour.
- ✅ Env var names, screenshot names and report labels are consistent everywhere they are used.
- ❌ Opening a page object no longer shows its selectors inline; jump to the `*Locators` group (one click in an IDE).
- ❌ Log, exception and Allure step texts stay inline on purpose: they are prose, not values, and are easier to read at the call site.

---

## ADR-10 — Cart check: the "Items" row of the order summary, read on the cart page

**Context.** Spec 5.4 asks to open the cart, read the subtotal/total as the site shows it, and assert it is not above `budget_per_item * items_count`, with a screenshot/trace of the cart page. Probing the live cart (`cart.ebay.com`, 2026-10, guest, from Israel) showed:
- The cart is on its own host. The header cart icon (`.gh-cart a.gh-flyout__target`) links to it. Other header links contain `cart.ebay.com` too, inside their sign-in `?ru=` parameter.
- The order summary (`[data-test-id=cart-summary]`) has an "Item (1)" / "Items (n)" row (`ITEM_TOTAL`) and a "Subtotal" row (`SUBTOTAL`). Both are in the **same currency as the search results** (ILS 210.70). The subtotal adds shipping when eBay can quote it.
- Each line shows the price in the **listing's** currency first, then the converted one: "US $68.99 (ILS 210.70)".
- eBay's own `data-test-id` attributes are on every part the check needs. The layout classes around them are generic (`val-col`, `table`).
- Opening the cart is one more navigation that can get a bot check (it did once during probing).

**Decision.**
- `CartService.assert_cart_total_not_exceeds(budget_per_item, items_count)` ([services/cart_service.py](../services/cart_service.py)) opens the cart through `Header.open_cart()`, then `CartPage` ([pages/cart_page.py](../pages/cart_page.py)) waits for the summary and reads the total with the shared price parser.
- The total checked is the **"Items" row** by default: the sum of the item prices, which is what the search price filter compared (ADR-7, shipping excluded). `cart.total_line: subtotal` in the profile switches the check to the subtotal row (items plus shipping) for a stricter run.
- The comparison is in **cents** (`round(total, 2) <= round(budget, 2)`), so 3 × 0.10 is not "above" 0.30 through float error.
- A failure raises `CartBudgetExceededError`, a subclass of `AssertionError`, so pytest reports a failed check and not a broken test. The message has the actual value, the budget, how it was computed, and the excess: `Cart items ILS 675.50 is above the budget 660.00 (220 per item x 3 items), over by 15.50`.
- `check_cart_total()` does the same reading without the assertion and returns a `CartCheck` (total, budget, cart lines) for tests and reports. `assert_cart_total_not_exceeds()` is a thin wrapper over it.
- Evidence comes before the verdict: a full-page screenshot of the cart and a "Cart total vs. budget" text attachment (total, budget, verdict, one row per cart line) are saved before the check can fail. The cart steps are wrapped in a `tracing.group("Cart page")`, so they show as one labelled block in the trace viewer. `TRACE=on` (new env override) keeps the trace of a passing run too; by default (`retain-on-failure`) it is kept when the run fails.
- A cart line count that differs from `items_count` is logged as a warning. The e2e test asserts it, but the spec's function only compares totals.

**Alternatives.**

| Option | Why not |
|---|---|
| Check the "Subtotal" row by default | It includes shipping, which the search never checked (ADR-7). A run would fail on a cheap item with expensive shipping, for a reason the search could not prevent. Kept as an opt-in. |
| Sum the line prices | Lines are in the listing's currency ("US $68.99") with the converted price in brackets. The summary row is already in the search's currency and is what eBay shows as the total. |
| `page.goto("https://cart.ebay.com")` | Another host than `base_url`, and a cold deep link is more likely to get a bot check. The header link is what a user clicks. |
| Plain `assert` in the test | The spec defines the check as a function; keeping it in the service gives one message format and one evidence path for every caller. |
| Save a separate trace chunk for the cart page only | Ending a chunk mid-test would cut the failure trace the fixture saves at the end. A trace group labels the cart steps without splitting the trace. |

**Consequences.**
- ✅ The cart locators are tested offline against copied markup ([tests/unit/test_cart_page.py](../tests/unit/test_cart_page.py)), and the check (pass, equal, above budget, subtotal line, message format, trace group) with stubbed pages ([tests/unit/test_cart_service.py](../tests/unit/test_cart_service.py)).
- ✅ A failing check reads as actual vs. budget in the pytest output and the Allure report, next to the cart screenshot.
- ❌ With the default `items` line, shipping costs never fail the check. This is documented in the README.
- ❌ The cart page was probed as a guest with one listing that does not ship to Israel (no shipping row). The subtotal row is read the same way, but its shipping content was not seen live.

## ADR-11 — Full scenario test and three reports per run

**Context.** Stage 7 asks for one e2e test that runs search → add → assert from the data file with Allure steps, and for Allure results plus JUnit XML (and optionally pytest-html). Stage 6 already had `tests/e2e/test_cart_total.py` running the same three calls. Every live run costs eBay requests, and bursts of runs get a bot check (ADR-6). The Allure report needs the separate Allure CLI (Java), which a reviewer may not have installed.

**Decision.**
- The Stage 6 test became the scenario test: `tests/e2e/test_e2e_cart_budget.py` (renamed with `git mv`, kept under `tests/e2e/` with the other live tests instead of the plan's `tests/` root). It wraps the spec's three calls in numbered top-level Allure steps (`ScenarioStep`); the services' own steps, screenshots and attachments nest inside them. Spec 5.1 (session) runs in the `user_session` fixture, so Allure shows it under "Set up". The Allure title is built from the data row (`AllureTitle.CART_BUDGET`), and the test is tagged with feature "Full scenario" and severity critical.
- `pytest.ini` writes three reports on every run, all under `reports/`:
  - `allure-results/` — the main report: steps, screenshots, cart check, trace. `allure serve reports/allure-results`.
  - `junit.xml` — for CI dashboards (suite name `ness-ebay-e2e`).
  - `report.html` — pytest-html, self-contained, opens in any browser without the Allure CLI. Restyled by [assets/html_report.css](../assets/html_report.css) (`--css`, inlined into the file): cards, outcome pills, colored row edges, dark log panel, light/dark mode. CSS only, over pytest-html's own class names, so no template is overridden; system fonts only, since the file is opened offline.
- `pytest_sessionfinish` writes `allure-results/environment.properties` (profile, base URL, browser, headless, session, cart total line, trace mode, data file), so the Allure report shows which settings produced it. The same values go into the HTML report's "Environment" table (`pytest_metadata`).
- In the HTML report, a failed test's row embeds the failure screenshots and links to the saved trace ([utils/html_report.py](../utils/html_report.py)). The evidence is only created in the context fixture's teardown, so it is attached to the teardown report; pytest-html merges the extras of every phase into the test's row from 4.2 (4.1.x drops them), hence `pytest-html>=4.2`.

**Alternatives.**

| Option | Why not |
|---|---|
| Keep `test_cart_total.py` and add the scenario test next to it | Two tests running the same live flow per data row: double the eBay traffic and twice the bot-check risk, for no extra coverage. |
| Pass `--junitxml`/`--html` only in CI | The milestone is "one command gives the reports". Writing them always costs under a second. |
| Link the failure screenshots instead of embedding them | The report would break when moved or attached alone. Screenshots are only taken on failure, so embedding keeps the file small. The trace (several MB) is linked instead. |

**Consequences.**
- ✅ `pytest tests/e2e/test_e2e_cart_budget.py` runs the whole spec once per data row and leaves an Allure report, a JUnit file and an HTML report.
- ✅ A reviewer without the Allure CLI can still open `reports/report.html`.
- ❌ `pytest-html` is one more **required** dependency: `pytest.ini` always passes `--html`/`--css`, so pytest stops with "unrecognized arguments" without it. Its report has no steps and only the failure evidence; the step screenshots and the cart check are in Allure only.

## ADR-12 — Bot protection experiment: hide the automation flags (kept, off by default)

**Context.** eBay's bot protection is the main obstacle to checking that the project works and to debugging it. The code under test is the framework, not eBay's defenses, yet:
- Every headless run (the `ci` profile) gets "Error Page | eBay", so the pipeline can never show a green run.
- A few runs in a row get rate-limited even when headed. A fix can't be tried right after a failure: the retry fails at the home page with `BotChallengeError` and never reaches the code that was changed.
- A failure caused by eBay's protection hides real failures (a changed selector, a broken step) behind the same bot page.

ADR-6 decided not to work around the protection. On a separate branch (`try-to-fix-bot-bot-protection`) we measured whether hiding the usual automation markers would make headless runs usable, so the decision rests on data instead of an assumption.

**What was tried** (headless, one run each, spaced out, from an Israeli IP):

| Setup | Result |
|---|---|
| Bundled Chromium + `STEALTH=true`: `--disable-blink-features=AutomationControlled`, no `--enable-automation`, `navigator.webdriver` hidden, `HeadlessChrome` removed from the real UA, full Chromium instead of the headless shell | Bot page |
| Installed Chrome (`BROWSER_CHANNEL=chrome`) | Bot page |
| Installed Edge (`BROWSER_CHANNEL=msedge`) | Bot page |
| Firefox | Bot page |
| WebKit | Home page once, then the bot page on all 4 smoke tests a minute later |

The trace of the stealth run shows why: the **first** request, `GET https://www.ebay.com/`, already returns **403**, before any page script runs. eBay decides from the IP, the TLS/HTTP fingerprint and the request headers, which script-level patches (this module, or `playwright-stealth`, which patches the same JavaScript properties) cannot change. The WebKit pass is not reproducible: either eBay's scoring varies from request to request, or the burst of test runs had rate-limited the IP. Telling the two apart needs more traffic against eBay, which is not worth it.

**Decision.**
- Keep the code as an **opt-in** setting, `browser.stealth` (env `STEALTH`, default `false`), in [core/stealth.py](../core/stealth.py), Chromium only. When it is off, the launch and context options are exactly the ones from before (guarded by [tests/unit/test_stealth.py](../tests/unit/test_stealth.py)). It hides automation markers only; it never solves or bypasses a CAPTCHA, and a bot page is still reported by `ensure_not_blocked()`.
- Add `browser.channel` (env `BROWSER_CHANNEL`): drive an installed Chrome/Edge instead of the bundled Chromium. Useful on its own, e.g. to reproduce a bug in the browser a user actually has.
- `base.yaml` now matches where the runs come from: `timezone_id: Asia/Jerusalem` and `currency: ILS` (eBay shows ILS from Israel anyway, ADR-7). `locale` stays `en-US` so the UI stays English.
- ADR-6 stands: run headed, keep traffic low, fail fast with a screenshot when blocked.

**Alternatives.**

| Option | Why not |
|---|---|
| Go further: copy a real browser's TLS/HTTP2 fingerprint, rewrite client-hint headers, residential proxies | Real evasion work against the site's protection, out of scope (MISSION_PLAN §5.1), and brittle: it breaks when eBay updates its checks. |
| Add `playwright-stealth` | Same layer as `core/stealth.py`: page scripts. The block happens on the first request, before they run. |
| Delete the experiment | The measurements and the toggle let anyone check the result again in one command (`STEALTH=true HEADLESS=true pytest -m smoke`) instead of repeating the work. |

**Consequences.**
- ✅ Headless being blocked is now measured, not assumed: on the first request, whatever the browser. It supports the "run headed" rule of ADR-6.
- ✅ `BROWSER_CHANNEL` and the Israel timezone/currency are useful without stealth (no currency-mismatch warning anymore).
- ❌ The repo now has code meant to hide automation, which ADR-6 rejects as a solution. It stays off by default and is documented here as a failed experiment, not as a way to run the tests.
- ❌ CI stays red against live eBay. Proving the framework works still needs a headed run on a desktop, and the offline unit tests remain the reliable check for selectors and logic.

---

## ADR-13 — Sign-in form tests: step-level `LoginPage`, few failed attempts, a full stop of tracing

**Context.** With a test account in `.env`, the sign-in form can be tested on its own: wrong password, unknown account, and so on. Probing it live (Playwright MCP, headed, 2026-10) showed:
- Two steps on `signin.ebay.com`. Continue is handled inside the page (the URL stays the same). Sign in posts a form, and the answer is a new page: `/signin/s` with the error, or a redirect to the home page.
- Errors appear in `#signin-error-msg`: "Oops, that's not a match." (empty username), "We couldn't find this eBay account…", "This password is incorrect…". A rejected password also empties the field.
- On the username step the (hidden) `#pass` is already in the DOM. `LoginPage` waited on `#pass.or_(#signin-error-msg).first`, and `.first` picks the first match **in DOM order**, which is the hidden field. So a rejected username ended in a timeout reported as "2FA or a passkey prompt?" instead of eBay's error.
- The username is trimmed and not case-sensitive. "Switch account" goes back to an empty username step. "Reset your password" leads straight to a captcha page.
- A Playwright trace keeps request bodies in its network log **across chunks**. With the old `stop_chunk()`/`start_chunk()` pause, the form POST `pass=<password>` was still in the saved trace (shown by experiment, now covered by a unit test).

**Decision.**
- `LoginPage` exposes the steps: `submit_username`, `submit_password`, `switch_account`, and getters for the state (`error_text`, `is_on_username_step`, `is_on_password_step`, `account_shown`, `is_sign_in_enabled`, …). The steps **return** with eBay's inline error, so tests can check it. `sign_in` is built on top of them and still raises `LoginError` naming the rejected step.
- The wait only looks at visible elements (`.filter(visible=True).first`). This needs Playwright ≥ 1.51.
- `submit_password` waits for a navigation before reading the answer. Otherwise, on a second try, the error left from the first try would be read as the answer. If no new page comes (an answer inside the page), the step fails like any stuck step: bot-check detection first, then `LoginError`, not a bare Playwright timeout.
- `LoginPage.submit_password` pauses tracing itself, so every caller is covered. `AuthService` no longer pauses (the two pauses would nest). `tracing_paused` now does a full `tracing.stop()` / `tracing.start()` with the fixture's options (`TRACE_START_OPTIONS`).
- Live tests in [tests/e2e/test_login.py](../tests/e2e/test_login.py) (marker `login`) open the form from the home page header (`AuthService.open_sign_in_page`). Those that need the account take `account_login_page`, which depends on `account`, so without credentials they are skipped **before** anything is opened on eBay. Expected texts are fragments, in `LoginErrorText`.
- Offline: [tests/unit/test_login_page.py](../tests/unit/test_login_page.py) runs `LoginPage` against a routed stand-in for the form, so the waiting logic is checked without eBay's rate limits.

**Alternatives.**

| Option | Why not |
|---|---|
| Keep `sign_in` only, and check that it raises `LoginError` | It can't check what eBay showed (the error text, which step, an emptied field), and one bad step hides the rest. |
| Many data-driven wrong passwords (empty, too long, SQL-like, …) | Every failed attempt counts against the real account, and eBay locks it or sends it to a captcha. A run makes three failed attempts on purpose, and the offline tests cover the logic. |
| Test "Reset your password" | It goes straight to a captcha, which is out of scope (MISSION_PLAN §5.1). |
| Keep `stop_chunk()` and also hide the POST (route it, or strip the HAR entry) | More code for the same result. A full stop drops everything, network included, and needs nothing else. |

**Consequences.**
- ✅ A rejected username is reported with eBay's own message, in about a second instead of a 15 s timeout.
- ✅ The password is out of the trace's snapshots **and** its network log, checked offline on every unit run.
- ❌ Each live test opens the home page again, so `pytest -m login` is a burst that eBay's rate limit can cut off ("Error Page" at setup). Space the runs out, or run single tests.
- ❌ A trace of a signed-in run starts after the sign-in, as before. Its title (the test id) is kept: the fixture starts tracing through `utils.tracing.start_tracing`, which remembers the title for the restart.
- ❌ The live tests depend on eBay's English texts and on the account staying in good standing.
- *Update (2026-10): passkey offer.* After a correct password eBay may show "Simplify your sign-in" (`accounts.ebay.com/acctsec/authn-register`) and offer to create a passkey. That needs a real authenticator, so `submit_password` clicks "Skip for now" (`#passkeys-cancel-btn`), which goes on to the home page, signed in. This is an optional step eBay offers, not a bot check, so declining it fits ADR-6. Before this, every signed-in run that got the offer failed with "2FA or a passkey prompt?". Covered offline by `test_passkey_offer_after_the_password_is_skipped`.
