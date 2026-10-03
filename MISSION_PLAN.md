# Ness Take-Home Assignment — Mission Plan

## 1. Goal
1. Build an **E2E scenario on eBay**: search products → filter by price → add to cart → assert the cart total.
2. Show a **clean architecture**: Page Object Model, OOP, data-driven.

## 2. Time Box
- **3–4 net hours** of implementation.
- **20–30 min** for the walkthrough/demo.

## 3. General Requirements
| Area | Choice |
|---|---|
| Automation | Playwright |
| Language | Python |
| Reports | Allure (alternatives: Extent Reports, Report Portal) |
| Design | Self-developed **POM** |
| Test data | **Data-driven** from an external file (JSON / CSV / YAML) |

## 4. Grading Criteria
| Weight | Criterion |
|---|---|
| **45%** | Architecture & clean code: POM, OOP, SRP, utils |
| **35%** | Robustness & smart locators: dynamic content, paging, variant selection, price parser |
| **15%** | Data-driven: config, ENV, profiles |
| **15%** | Reports/docs: clear README, reports, screenshots |

## 5. Core Functions (spec)

### 5.1 Login
Login is required, but a **guest / stub** login is allowed (document it as a limitation).

**CAPTCHA is out of scope:** there is no need to solve, bypass or work around eBay's CAPTCHA / bot checks. When one appears, the run stops with a clear `BotChallengeError` and a screenshot, and the limitation is documented in the README.

### 5.2 `search_items_by_name_under_price(query, max_price, limit=5) -> list[str]`
- Search by `query`.
- If the page has a price filter (min/max), use it to narrow the results.
- Use **XPath** to collect the first `limit` items whose price is **≤ `max_price`**.
- If the current page has fewer than `limit` matches:
  - if there is paging ("Next" button / page links), go to the next page and keep collecting until `limit` is reached or the pages run out;
  - if there is no paging, return what was found (even if fewer than `limit`).
- Returns a list of up to `limit` item URLs. Returning fewer, even 0, is valid.
- Example: `urls = search_items_by_name_under_price("shoes", 220, 5)`

### 5.3 `add_items_to_cart(urls: list[str]) -> None`
- Loop over the URLs and open each item page.
- If the item has variants (size/color/quantity), pick **random available** values.
- Click **"Add to cart"**.
- Go back to the search screen/tab.
- Save a **screenshot + log** for each item added.

### 5.4 `assert_cart_total_not_exceeds(budget_per_item: float, items_count: int) -> None`
- Open the cart.
- Read the subtotal/total as shown on the site.
- Compute the threshold: `budget_per_item * items_count`.
- Assert that the total is **not above** the threshold.
- Save a **screenshot/trace** of the cart page.

### 5.5 Full scenario example
1. `search_items_by_name_under_price("shoes", 220, 5)` → up to 5 URLs.
2. `add_items_to_cart(urls)` → all of them are added to the cart.
3. `assert_cart_total_not_exceeds(220, len(urls))` → cart total ≤ 220 × item count.

---

## 6. Stages & Milestones

### Stage 0 — Project Setup (~20 min) ✅ DONE
- [x] `requirements.txt` / `pyproject.toml`: `playwright`, `pytest`, `pytest-playwright`, `allure-pytest`, `pyyaml`, `python-dotenv`.
- [x] `playwright install chromium`.
- [x] `.gitignore` (venv, `__pycache__`, `reports/`, `allure-results/`, `.env`).
- [x] Folder skeleton:
  ```
  config/      # env profiles: base.yaml + dev.yaml / ci.yaml
  core/        # config loader, logger, base classes
  pages/       # page objects (Home, Login, SearchResults, Item, Cart)
  components/  # reusable UI parts (header search bar, variant selector, pagination)
  services/    # business flows composed from pages (AuthService; later search/cart)
  utils/       # price parser, screenshot/attachment helpers
  data/        # test data (YAML/JSON)
  tests/       # e2e + unit tests
  reports/     # generated reports (gitignored)
  ```

> ✅ **Milestone 0:** `pytest` runs a smoke test that opens ebay.com (headed and headless).

### Stage 1 — Framework Core & Config (~30 min) ✅ DONE
- [x] `BasePage`: navigation, waits, safe click, element text, screenshot helper.
- [x] Logger (console + file).
- [x] Config loader: `ENV` variable + profiles (e.g. `dev`, `ci`) → base URL, headless, timeouts, slow-mo, locale/currency.
- [x] `conftest.py` fixtures: browser/context/page, tracing on, screenshot on failure, Allure attachments.
- Note: replaced the `pytest-playwright` plugin with our own fixtures so the profile (not CLI flags) controls the browser. Rationale and trade-offs: [docs/DECISIONS.md](docs/DECISIONS.md).
- [x] `BROWSER` env var override (alongside `BASE_URL`, `HEADLESS`, `SLOW_MO`).

> ✅ **Milestone 1:** profile switchable via `ENV=ci pytest`; a failing test produces a screenshot and trace in the report.

### Stage 2 — Data-Driven Test Data (~15 min) ✅ DONE
- [x] `data/search_cases.yaml` with rows like `{query: shoes, max_price: 220, limit: 5}`. Loaded by `core/data_loader.py` into validated `SearchCase` rows (optional `budget_per_item`, `id`).
- [x] Credentials / guest flag from `.env` (never committed; provide `.env.example`). `auth.guest` in the profile, `EBAY_GUEST` / `EBAY_USERNAME` / `EBAY_PASSWORD` from the environment.
- [x] Parametrize tests from the data file: any test that takes a `search_case` argument runs once per row (`pytest_generate_tests`). Rationale: [docs/DECISIONS.md](docs/DECISIONS.md) ADR-5.
- Note for Stage 4: in headless mode, a cold deep link to `/sch/...` returns eBay's "Error Page", and a burst of runs triggers "Pardon Our Interruption" (bot challenge) even when headed. Search from the home page and report the challenge page explicitly (no CAPTCHA handling, see 5.1).

> ✅ **Milestone 2:** adding a row to the data file adds a test case with no code changes.

### Stage 3 — Login (~15 min) ✅ DONE
- [x] `LoginPage` / `AuthService`: guest mode by default (eBay shows captcha/bot protection on sign-in); real login behind a config flag.
  - `services/auth_service.py` (`AuthService.start_session() -> UserSession`), `pages/home_page.py`, `pages/login_page.py`, `components/header.py`; `user_session` fixture in `tests/conftest.py`.
  - The header component closes the "Are you shipping to …?" modal, which blocks every click on the page.
  - `BasePage.open()` detects bot-check pages ("Error Page", "Security Measure", "Pardon Our Interruption", `/splashui/captcha`) and raises `BotChallengeError` with a screenshot instead of timing out. Detection only: the CAPTCHA itself is not handled (out of scope, see 5.1).
  - Real sign-in (`EBAY_GUEST=false`) is implemented but not verified end to end: no test account, and headless sign-in always redirects to a captcha. Rationale: [docs/DECISIONS.md](docs/DECISIONS.md) ADR-6.

> ✅ **Milestone 3:** session is ready as guest; the limitation is noted in the README.

### Stage 4 — Search with Price Condition (~50 min) ✅ DONE
- [x] `SearchResultsPage`: run the search and apply the min/max price filter (fall back to URL params such as `_udhi` if the UI filter is missing).
  - `services/search_service.py` (`SearchService.search_items_by_name_under_price()` + `find_items_under_price()`), `pages/search_results_page.py`, `components/price_filter.py`; `Header.search()` searches from the current page (a cold deep link to `/sch/` gets the bot page).
- [x] XPath locators for item cards, title, price, link; skip placeholder cards ("Shop on eBay").
  - Placeholder cards, carousels and "Results matching fewer words" cards are skipped. Auction-only cards are skipped too (they cannot be added to a cart).
  - Deviation from the original plan: sponsored cards are **kept**, not skipped. They are real listings that match the query and price, and the new layout hides the "Sponsored" label behind obfuscated markup (ADR-7).
- [x] `utils/price_parser.py`: handles currency symbols, commas, ranges ("$10.00 to $25.00" → take the upper bound when checking against max), and "free"/missing price.
- [x] Pagination component: click "Next" until `limit` is reached or there is no next page (capped by `search.max_pages` in the profile).
- [x] Unit tests for the price parser (plus offline XPath tests against copied card markup, URL helpers, match rules).
- Note: eBay shows prices in the visitor's currency (ILS from Israel), so `max_price` is compared in the displayed currency. Rationale: [docs/DECISIONS.md](docs/DECISIONS.md) ADR-7.

> ✅ **Milestone 4:** `search_items_by_name_under_price("shoes", 220, 5)` returns ≤ 5 URLs, all priced ≤ 220; price parser unit tests pass.

### Stage 5 — Add Items to Cart (~45 min) ✅ DONE
- [x] `ItemPage` + `VariantSelector` component: detect variant dropdowns/buttons, pick a random **available** value, set quantity.
  - `services/cart_service.py` (`CartService.add_items_to_cart()` + `add_items()`), `pages/item_page.py`, `components/variant_selector.py`, `components/added_to_cart_dialog.py`. Quantity stays at 1 so the Stage 6 budget check holds; variant picks come from a logged seed (`RANDOM_SEED` replays them).
- [x] Handle dynamic cases: out-of-stock options, overlays/popups, "See all options", items opened in a new tab.
  - Out-of-stock values are skipped and dimensions are picked in order (a pick changes what the next one offers). "See all options" was not found on live pages and is not handled (ADR-8).
- [x] Click "Add to cart", close the cart dialog, navigate back.
  - Each item opens in its own tab, which is closed afterwards: the search tab is never left.
- [x] Screenshot + log per item, attached to Allure.

> ✅ **Milestone 5:** every URL from Stage 4 is added to the cart, with one screenshot per item in the report.

### Stage 6 — Assert Cart Total (~25 min) ✅ DONE
- [x] `CartPage`: open the cart and read the subtotal with the price parser.
  - `pages/cart_page.py`, `Header.open_cart()`, `CartService.assert_cart_total_not_exceeds()` + `check_cart_total()`; e2e test `tests/e2e/test_cart_total.py` (became the Stage 7 scenario test).
  - Reads the order summary's "Items (n)" row by default (item prices only, like the search filter); `cart.total_line: subtotal` checks items + shipping instead (ADR-10).
- [x] Compute `budget_per_item * items_count` and assert `total <= budget`, with a clear failure message (actual vs. budget).
  - Raises `CartBudgetExceededError` (an `AssertionError`): `Cart items ILS 675.50 is above the budget 660.00 (220 per item x 3 items), over by 15.50`. Compared in cents.
- [x] Screenshot + trace of the cart page.
  - Full-page screenshot + "Cart total vs. budget" attachment before the verdict; cart steps grouped as "Cart page" in the trace; `TRACE=on` keeps the trace of a passing run.

> ✅ **Milestone 6:** the assertion passes for the full scenario; a forced failure shows a readable message.

### Stage 7 — E2E Test & Reports (~20 min) — code done, live green run pending
- [x] `tests/test_e2e_cart_budget.py`: search → add → assert, parametrized from the data file, with Allure steps.
  - Lives at `tests/e2e/test_e2e_cart_budget.py` (with the other live tests); it replaces the Stage 6 `test_cart_total.py` so the same flow is not run twice against eBay. Numbered top-level steps per spec function, title built from the data row (ADR-11).
- [x] Reports: Allure results + JUnit XML (`--junitxml=reports/junit.xml`) + optional `pytest-html`.
  - All three are written by every run (`pytest.ini`): `reports/allure-results/`, `reports/junit.xml`, `reports/report.html` (self-contained, no Allure CLI needed). The Allure report also gets an "Environment" widget with the run's profile.

> ✅ **Milestone 7:** one command gives a green run and an Allure report with steps, screenshots and trace.

### Stage 8 — Bug Exercise: `ReadMeAIBugs.md` (~20 min) ✅ DONE
Static review of the AI-generated snippet: find **at least 3 bugs**, explain each in detail, and propose fixed code.

Bugs to cover:
1. **Mixed frameworks:** `from selenium import webdriver` is unused and has nothing to do with Playwright.
2. **Resource leak:** `sync_playwright().start()` is never stopped, and `browser.close()` is skipped if anything fails. Fix: `with sync_playwright() as p:` plus `try/finally`, or a pytest fixture.
3. **Hard waits:** `time.sleep(2)` and `time.sleep(3)` are slow and flaky. Fix: rely on Playwright auto-waiting and `expect(...)`.
4. **No assertion:** `results` is created but never checked, so the test always passes. Fix: `expect(results.first).to_be_visible()` / `expect(results).not_to_have_count(0)`.
5. **Weak locators:** the generic `.button` can match many elements (strict mode violation) or the wrong one. Fix: `page.get_by_role("button", name="Search")`.
6. **Wrong target:** `https://example.com` has no `#search` box, so the test cannot work. The URL is also hard-coded instead of coming from config.

- [x] Include the full corrected snippet.
  - [ReadMeAIBugs.md](ReadMeAIBugs.md): 8 issues (4 main, 4 minor), each with an explanation and fix, plus the full corrected version (pytest-playwright `page` fixture) and a summary table.

> ✅ **Milestone 8:** `ReadMeAIBugs.md` lists ≥ 3 bugs, each with an explanation and fixed lines.

### Stage 9 — README & Delivery (~20 min)
- [x] README: prerequisites, installation, run commands (per ENV/profile), how to generate/open reports.
- [ ] Short architecture explanation (folder tree + layers).
- [ ] Limitations/assumptions: guest login stub, captcha/bot detection (not handled, out of scope), regional pricing/currency, dynamic DOM, sponsored items, shipping not included in the price filter.
- [ ] Push to GitHub and confirm the repo is accessible.

> ✅ **Milestone 9:** fresh clone → follow the README → tests run and the report opens.

---

## 7. Final Delivery Checklist
| Requirement (from instructions) | Stage |
|---|---|
| Playwright + Python | 0 |
| Self-developed POM, OOP, SRP, utils | 1, 4–6 |
| Data-driven from external file (JSON/CSV/YAML) | 2 |
| Config / ENV / profiles | 1 |
| Login (guest/stub allowed) | 3 |
| Search with price filter + XPath + paging | 4 |
| Price parser | 4 |
| Add to cart with random variants + screenshot/log per item | 5 |
| Assert cart total ≤ budget × count + screenshot/trace | 6 |
| Full E2E scenario | 7 |
| Report (Allure / HTML / JUnit XML) | 7 |
| `ReadMeAIBugs` with ≥ 3 bugs, explanations, fixes | 8 |
| README: how to run, architecture, limitations | 9 |
| GitHub link with access | 9 |
