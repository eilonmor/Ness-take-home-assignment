# Ness-take-home-assignment

E2E scenario on eBay with Playwright + Python: search → filter by price → add to cart → assert the cart total.
Spec and stage tracker: [MISSION_PLAN.md](MISSION_PLAN.md). Design decisions: [docs/DECISIONS.md](docs/DECISIONS.md). Bug exercise (review of the AI-generated snippet): [ReadMeAIBugs.md](ReadMeAIBugs.md).

## Contents

- [Prerequisites](#prerequisites)
- [Setup](#setup)
- [Configuration](#configuration)
- [Running the tests](#running-the-tests)
  - [Troubleshooting](#troubleshooting)
- [Reports](#reports)
- [Architecture](#architecture)
- [Limitations](#limitations)
  - [Login: guest session by default](#login-guest-session-by-default)
  - [Bot detection](#bot-detection)
  - [Search and prices](#search-and-prices)
  - [Add to cart](#add-to-cart)
  - [Cart total check](#cart-total-check)
  - [Dynamic pages and locators](#dynamic-pages-and-locators)

## Prerequisites

| Tool | Version | Required? | Needed for |
|---|---|---|---|
| Python | 3.11+ (developed on 3.14) | Required | Running the tests (`typing.Self`) |
| Git | any | Required | Cloning the repo |
| JDK | 21+ | Optional | Running the Allure CLI (it is a Java app). Set `JAVA_HOME` to the JDK folder. Install with `winget install Microsoft.OpenJDK.21` (Windows) or `brew install openjdk@21` (macOS). |
| Allure CLI | 2.x | Optional | Viewing the Allure report (`allure serve`). Install with `scoop install allure` (Windows), `brew install allure` (macOS) or `npm install -g allure-commandline`. |

The tests run without the two optional tools: every run still writes the Allure results, and the HTML and JUnit reports need neither.

A desktop session with a visible browser is also needed: eBay blocks headless browsers (see [Bot detection](#bot-detection)).

## Setup

```bash
git clone https://github.com/eilonmor/Ness-take-home-assignment.git
cd Ness-take-home-assignment

python -m venv .venv
.venv\Scripts\activate          # Windows (PowerShell)
source .venv/bin/activate       # macOS / Linux

pip install -r requirements.txt
python -m playwright install chromium

cp .env.example .env            # optional: local overrides, git-ignored
pytest --collect-only           # sanity check: validates the profile, .env and data file
```

## Configuration

Settings are layered; each layer overrides the one before it:

1. [config/base.yaml](config/base.yaml): defaults for every profile (base URL, browser, timeouts, artifacts, search and cart options).
2. `config/<profile>.yaml`: the keys a profile changes.
   - `dev` (default): headed, `slow_mo` 100 ms, DEBUG logs.
   - `ci`: headless, longer timeouts. eBay will most likely block it (see [Bot detection](#bot-detection)).
3. Environment variables, from the shell or from `.env`.

**Choosing a profile:** `pytest --env ci`, or `ENV=ci` in the environment / `.env`. Without either, `dev` is used.

**One-off overrides** (environment or `.env`):

| Variable | Example | Effect |
|---|---|---|
| `HEADLESS` | `false` | Show or hide the browser |
| `SLOW_MO` | `250` | Delay between actions (ms) |
| `BROWSER` | `firefox` | `chromium`, `firefox` or `webkit` (install the extra browsers with `python -m playwright install firefox webkit`) |
| `BASE_URL` | `https://www.ebay.co.uk` | Another eBay site |
| `TRACE` | `on` | Keep the Playwright trace of passing runs too (default: only failed runs) |
| `RANDOM_SEED` | `12345` | Replay the random variant picks of an earlier run (the seed is logged) |
| `EBAY_GUEST`, `EBAY_USERNAME`, `EBAY_PASSWORD` | | Real sign-in instead of guest (see [Login](#login-guest-session-by-default)). Credentials are read only from the environment, never from profiles. |

PowerShell syntax: `$env:HEADLESS="false"; pytest`. Bash: `HEADLESS=false pytest`.

**Test data:** [data/search_cases.yaml](data/search_cases.yaml). Each row is one test case: `query`, `max_price`, optional `limit` (default 5), `budget_per_item` (default `max_price`) and `id` (test name in the reports). Adding a row adds a test, with no code change.

## Running the tests

```bash
pytest tests/e2e/test_e2e_cart_budget.py   # the full scenario: search → add to cart → cart total check, once per data row
pytest tests/e2e                           # every live test (smoke + scenario steps)
pytest -m e2e                              # only the scenario tests (search, add to cart, cart total)
pytest -m smoke                            # quick checks: home page, session, search page
pytest tests/unit                          # offline unit tests, no browser or eBay needed
pytest                                     # everything
```

- A single data row: `pytest "tests/e2e/test_e2e_cart_budget.py::test_cart_total_not_exceeds_budget[shoes-under-220]"`.
- The live tests open a real browser on eBay. Running many of them back to back can trigger eBay's rate limiting. The run then stops with `BotChallengeError`; wait a few minutes (sometimes longer) before retrying.

### Troubleshooting

**`pytest : The term 'pytest' is not recognized as the name of a cmdlet, function, script file, or operable program.`**

pytest is installed inside the project's virtual environment (`.venv`), which is not active in this terminal. Activate it, then run the tests again:

```powershell
.venv\Scripts\activate
pytest tests/e2e/test_e2e_cart_budget.py
```

When it is active, the prompt starts with `(.venv)`. Activation lasts for that terminal only, so repeat it in every new terminal. On macOS / Linux: `source .venv/bin/activate`.

Two related cases:
- **`.venv\Scripts\activate` fails with "running scripts is disabled on this system"**: PowerShell blocks scripts by default. Allow them for your user once with `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`, then activate again.
- **No activation at all:** call the venv's Python directly, e.g. `.venv\Scripts\python -m pytest tests/e2e/test_e2e_cart_budget.py`.

## Reports

Every `pytest` run writes all of its output under `reports/` (git-ignored). The Allure results, `report.html`, `junit.xml` and `run.log` are **replaced** by each run. Screenshots and traces are **kept**: their file names start with a timestamp (`20261003-150113-249_...`), so files from earlier runs pile up next to the new ones. Match them to a run by that timestamp, or empty `reports/screenshots/` and `reports/traces/` before a run you want to keep separate.

| Report | Location | Created | How to open |
|---|---|---|---|
| **Allure** (main report) | `reports/allure-results/` | Every run. The folder is emptied at the start of the run (`--clean-alluredir`). | `allure serve reports/allure-results`: builds the report and opens it in the browser. For a static copy: `allure generate reports/allure-results -o reports/allure-report --clean`, then `allure open reports/allure-report`. |
| **HTML** | `reports/report.html` | Every run, at the end of the run. | Open the file in a browser (`start reports\report.html` on Windows). It is one self-contained file, with no tool needed. Do not use VS Code's preview: it blocks the report's scripts. |
| **JUnit XML** | `reports/junit.xml` | Every run, at the end of the run. | For CI dashboards (Jenkins, GitHub Actions, Azure DevOps). |
| Screenshots | `reports/screenshots/*.png` | Step screenshots on every run (session ready, each search results page, each item added, the cart page). A full-page screenshot of every open tab when a test fails. Kept across runs (timestamped names). | Any image viewer; also attached to the Allure report. |
| Playwright traces | `reports/traces/*.zip` | When a test fails (default), or for every test with `TRACE=on`. Kept across runs (timestamped names). | `playwright show-trace reports/traces/<file>.zip`, or drag the file onto [trace.playwright.dev](https://trace.playwright.dev). |
| Log | `reports/logs/run.log` | Every run (rewritten each time). | Any text editor. |

**What each report shows:**
- **Allure:** one entry per test and data row, with numbered steps (search → add to cart → cart total) and the services' sub-steps. Inside them: the step screenshots, the list of items found, the items added (with the variant seed), and the "Cart total vs. budget" attachment. Failed tests also carry the failure screenshots and the trace. The **Environment** widget shows the run's settings (profile, base URL, browser, headless, session, trace mode, data file).
- **HTML:** pass/fail per test with filters, the captured log of each test, the same environment settings, and for failed tests the failure screenshot and a link to the trace. It has no steps; use Allure for those.
- **JUnit XML:** pass/fail and failure messages only.

## Architecture

A self-developed Page Object Model in layers. Each layer uses only the layers below it:

```
tests/  →  services/  →  pages/  →  components/  →  core/ + utils/
```

| Layer | What it holds | Rule |
|---|---|---|
| `tests/` | pytest tests and fixtures | Calls services and page objects. No raw selectors. |
| `services/` | Business flows: the three spec functions plus session setup | Composes pages. Adds Allure steps and evidence. |
| `pages/` | One class per eBay page | Knows a page's locators and actions. No business rules. |
| `components/` | UI parts shared by pages or too large for one page (header, price filter, paging, variant pickers, cart dialog) | Same base class as the pages. |
| `core/` | Settings, base page, logger, data loader, exceptions, constants | Framework plumbing with no flow logic. `constants.py` also holds the selectors the pages use (ADR-9). |
| `utils/` | Small helpers with no browser state (price parser, URL helpers, report attachments, tracing) | Unit-tested offline. |

```
config/                 settings profiles: base.yaml + dev.yaml / ci.yaml
data/search_cases.yaml  test data, one test per row
core/
  config.py             base.yaml → <profile>.yaml → env vars, into frozen dataclasses
  base_page.py          BasePage: navigation, waits, bot-check detection, screenshots, logging
  constants.py          every fixed value: selectors/XPaths, URL paths, env var names, messages
  data_loader.py        reads and validates the data file into SearchCase rows
  exceptions.py         BotChallengeError, LoginError, AddToCartError, CartBudgetExceededError, ...
  logger.py             console + reports/logs/run.log
pages/                  HomePage, LoginPage, SearchResultsPage, ItemPage, CartPage
components/             Header, PriceFilter, Pagination, VariantSelector, AddedToCartDialog
services/
  auth_service.py       AuthService.start_session(): guest (default) or real sign-in
  search_service.py     search_items_by_name_under_price()        spec 5.2
  cart_service.py       add_items_to_cart(), assert_cart_total_not_exceeds()   spec 5.3, 5.4
utils/                  price_parser, urls, attachments, html_report, tracing, files
tests/
  conftest.py           browser/context/page fixtures, failure evidence, data-driven parametrize
  e2e/                  live tests against eBay (smoke + scenario steps + full scenario)
  unit/                 offline tests: price parser, XPaths on copied markup, config, data loader, ...
docs/DECISIONS.md       design decisions (ADR-1 … ADR-11)
```

**How a run fits together:**
1. `tests/conftest.py` loads the settings once per session and starts one browser. Each test gets a fresh context (empty cookies and cart), and its screenshots and trace are saved if it fails.
2. Any test that takes a `search_case` argument runs once per row of the data file.
3. The full scenario ([tests/e2e/test_e2e_cart_budget.py](tests/e2e/test_e2e_cart_budget.py)) follows spec 5.5: `user_session` (guest) → `SearchService.search_items_by_name_under_price()` → `CartService.add_items_to_cart()` → `CartService.assert_cart_total_not_exceeds()`.

**Design choices worth knowing** (details in [docs/DECISIONS.md](docs/DECISIONS.md)):
- Own fixtures instead of `pytest-playwright`, so the profile controls the browser and not CLI flags (ADR-1, ADR-2). `--headed` / `--browser` therefore do not exist: use `HEADLESS` / `BROWSER`.
- Site failures (bot check, item that cannot be added) raise their own exceptions. A budget overrun raises `CartBudgetExceededError`, an `AssertionError`, so the report tells "the site got in the way" apart from "the check failed".
- Fixed values in one `constants.py`, per-run values in the YAML profiles (ADR-9).

## Limitations

### Login: guest session by default
eBay protects sign-in with captcha and bot checks, so runs start as a **guest by default**. The spec allows a guest/stub login, and a guest can search and use the cart.

- The session is prepared by `AuthService` ([services/auth_service.py](services/auth_service.py)), which tests use through the `user_session` fixture. It opens the home page, closes the "Are you shipping to …?" dialog, and checks that the header shows a signed-out visitor.
- Real sign-in is opt-in: set `EBAY_GUEST=false` plus `EBAY_USERNAME` / `EBAY_PASSWORD` in `.env` (template: [.env.example](.env.example)). It is implemented but **not verified end to end**. If eBay asks for a captcha, 2FA or a passkey, the run stops with a clear `BotChallengeError` / `LoginError`.

### Bot detection
- Headless runs are blocked by eBay ("Error Page" / "Security Measure" captcha). Run headed: the default `dev` profile, or `HEADLESS=false`.
- Many runs in a short time are rate-limited even when headed. The run then fails fast with `eBay served a bot check (...)` and a screenshot. Wait a few minutes before retrying.

Design rationale: [docs/DECISIONS.md](docs/DECISIONS.md) ADR-6.

### Search and prices
- **Currency follows your location.** eBay shows prices in the visitor's currency (e.g. ILS from Israel), whatever the profile's `currency` says. `max_price` in [data/search_cases.yaml](data/search_cases.yaml) is compared in the displayed currency, and a mismatch is logged as a warning.
- **Item price only.** Shipping is not included in the price check.
- **What counts as a match:** the highest price on the card must be ≤ `max_price` (the upper bound of a range, the Buy It Now price of an auction). Auction-only listings are skipped because they cannot be added to a cart.
- **Sponsored listings are kept.** They are real listings that match the query and the price.
- **Paging is capped** at `search.max_pages` (default 5) to keep runs short and avoid eBay's rate limiting.

Design rationale: [docs/DECISIONS.md](docs/DECISIONS.md) ADR-7.

### Add to cart
- **One tab per item.** `CartService` ([services/cart_service.py](services/cart_service.py)) opens each item URL in a new tab, adds it, then closes the tab and returns to the search results tab.
- **Random variants are reproducible.** Values are picked at random among the *available* ones (out-of-stock values are skipped), one dimension at a time, because a pick removes the out-of-stock values from the other dimensions. The seed is logged and attached to the report; replay a run's picks with `RANDOM_SEED=<seed>`.
- **Quantity is always 1**, so the cart total can be compared with `budget_per_item × item count` (Stage 6).
- **Every add is confirmed** by eBay's "Added to cart" dialog and by the header cart count. A listing that cannot be added (ended, sold out, unknown variant widget) fails the run with `AddToCartError` and a screenshot, instead of being skipped.
- Only eBay's current variant dropdowns are supported; native `<select>` pickers and image swatches from older layouts are not.

Design rationale: [docs/DECISIONS.md](docs/DECISIONS.md) ADR-8.

### Cart total check
- **What is checked:** `CartService.assert_cart_total_not_exceeds(budget_per_item, items_count)` ([services/cart_service.py](services/cart_service.py)) opens the cart from the header and checks that the cart total is ≤ `budget_per_item × items_count`. `budget_per_item` comes from the data row (`budget_per_item`, default `max_price`).
- **Item prices, not shipping, by default.** The total read is the order summary's "Items (n)" row, the same item-price-only view the search filter used. Set `cart.total_line: subtotal` in a profile to check the subtotal (items + shipping) instead.
- **Currency:** the summary is in the same currency as the search results (e.g. ILS), so the budget is compared in that currency. Cart lines also show the listing's own currency ("US $68.99 (ILS 210.70)"); these are only reported, not summed.
- **Evidence:** a full-page cart screenshot and a "Cart total vs. budget" attachment (total, budget, verdict, cart lines) are saved before the check can fail. A failure reads like `Cart items ILS 675.50 is above the budget 660.00 (220 per item x 3 items), over by 15.50`.
- **Trace:** kept on failure by default; run with `TRACE=on` to keep it for a passing run too. The cart steps are grouped as "Cart page" in `playwright show-trace`.

Design rationale: [docs/DECISIONS.md](docs/DECISIONS.md) ADR-10.

### Dynamic pages and locators
- **Tied to eBay's current markup.** The locators target eBay's layout as of October 2026: `s-card` result cards, the current item-page variant dropdowns, and the cart's `data-test-id` hooks. eBay changes and A/B-tests its pages, so a redesign can break a locator. All of them live in [core/constants.py](core/constants.py), so a fix is made in one place.
- **No hard waits.** The framework waits for elements and page states (Playwright auto-waiting, `expect(...)`) and never sleeps for a fixed time. A page slower than the profile's `timeouts` still fails. The `ci` profile has longer timeouts.
- **Live data.** Results, prices and stock change from run to run, so two runs of the same data row add different items. A row can also find fewer than `limit` items. The scenario then checks the cart against the number it did add. If it finds none, the full scenario fails, because there is nothing left to check in the cart. The spec allows 0 results, so `search_items_by_name_under_price()` itself still returns an empty list.
- **Only verified against `ebay.com`, from Israel.** Other eBay sites (`BASE_URL`) and other regions may show different layouts, currencies or dialogs.
