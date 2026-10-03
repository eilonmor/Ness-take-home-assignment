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
- ✅ The password never reaches a trace. A trace stores every `fill()` value in plain text, and failing traces are attached to the report. So the sign-in runs inside `tracing_paused` ([utils/tracing.py](../utils/tracing.py)), and [tests/unit/test_tracing.py](../tests/unit/test_tracing.py) checks the trace zip for the secret.
- ❌ A trace of a real-login run starts after sign-in: the home page and the sign-in steps are dropped. A failed sign-in is still covered by the failure screenshot and the `LoginError` message.
- ❌ Real sign-in is implemented but not verified end to end (no test account, and headless always hits the captcha). Only the unknown-account error path was checked by hand.
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
