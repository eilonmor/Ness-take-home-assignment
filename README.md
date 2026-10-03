# Ness-take-home-assignment

E2E scenario on eBay with Playwright + Python: search → filter by price → add to cart → assert the cart total.
Spec and stage tracker: [MISSION_PLAN.md](MISSION_PLAN.md). Design decisions: [docs/DECISIONS.md](docs/DECISIONS.md).

## Prerequisites

| Tool | Version | Needed for |
|---|---|---|
| Python | 3.11+ (developed on 3.14) | Running the tests (`typing.Self`) |
| Git | any | Cloning the repo |
| Allure CLI | 2.x, needs Java 8+ | Viewing the Allure report only (`allure serve`). Install with `scoop install allure` (Windows), `brew install allure` (macOS) or `npm install -g allure-commandline`. |

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

## Reports

Every `pytest` run writes all of its output under `reports/` (git-ignored). Each run **replaces** the previous reports, so copy them elsewhere if you want to keep them.

| Report | Location | Created | How to open |
|---|---|---|---|
| **Allure** (main report) | `reports/allure-results/` | Every run. The folder is emptied at the start of the run (`--clean-alluredir`). | `allure serve reports/allure-results`: builds the report and opens it in the browser. For a static copy: `allure generate reports/allure-results -o reports/allure-report --clean`, then `allure open reports/allure-report`. |
| **HTML** | `reports/report.html` | Every run, at the end of the run. | Open the file in a browser (`start reports\report.html` on Windows). It is one self-contained file, with no tool needed. Do not use VS Code's preview: it blocks the report's scripts. |
| **JUnit XML** | `reports/junit.xml` | Every run, at the end of the run. | For CI dashboards (Jenkins, GitHub Actions, Azure DevOps). |
| Screenshots | `reports/screenshots/*.png` | Step screenshots on every run (session ready, each search results page, each item added, the cart page). A full-page screenshot of every open tab when a test fails. | Any image viewer; also attached to the Allure report. |
| Playwright traces | `reports/traces/*.zip` | When a test fails (default), or for every test with `TRACE=on`. | `playwright show-trace reports/traces/<file>.zip`, or drag the file onto [trace.playwright.dev](https://trace.playwright.dev). |
| Log | `reports/logs/run.log` | Every run (rewritten each time). | Any text editor. |

**What each report shows:**
- **Allure:** one entry per test and data row, with numbered steps (search → add to cart → cart total) and the services' sub-steps. Inside them: the step screenshots, the list of items found, the items added (with the variant seed), and the "Cart total vs. budget" attachment. Failed tests also carry the failure screenshots and the trace. The **Environment** widget shows the run's settings (profile, base URL, browser, headless, session, trace mode, data file).
- **HTML:** pass/fail per test with filters, the captured log of each test, the same environment settings, and for failed tests the failure screenshot and a link to the trace. It has no steps; use Allure for those.
- **JUnit XML:** pass/fail and failure messages only.

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
