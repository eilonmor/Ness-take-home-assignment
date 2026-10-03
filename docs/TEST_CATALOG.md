# Test Catalog

Every test in the suite, split into groups. For each test: **what it checks** and **the expected result**.

**186 tests collected**: 10 run against live eBay (E2E + smoke), 176 run offline (unit). A number like **(×N)** after a test name means it is parametrized and runs N times.

| Group | Files | Runs against | Tests |
|---|---|---|---|
| [1. Smoke (live eBay)](#1-smoke-tests-live-ebay) | `test_smoke.py`, `test_login.py`, `test_search_smoke.py` | live eBay | 4 |
| [2. E2E scenario (live eBay)](#2-e2e-scenario-tests-live-ebay) | `test_search.py`, `test_add_to_cart.py`, `test_e2e_cart_budget.py` | live eBay | 6 |
| [3. Search: XPath parsing and filtering](#3-search-result-parsing-and-filtering) | `test_search_results_page.py`, `test_search_service.py` | local HTML / stubs | 10 |
| [4. Cart: add-to-cart flow and budget check](#4-cart-add-to-cart-flow-and-budget-check) | `test_cart_service.py`, `test_cart_page.py` | stubs / local HTML | 17 |
| [5. Variant selection](#5-variant-selection-size--color) | `test_variant_selector.py` | local HTML | 24 |
| [6. Price parsing](#6-price-parsing) | `test_price_parser.py` | pure Python | 37 |
| [7. Configuration](#7-configuration-profiles-and-env-vars) | `test_config.py` | pure Python | 45 |
| [8. Test data loading](#8-test-data-loading-data-driven-cases) | `test_data_loader.py` | pure Python | 26 |
| [9. Bot detection and navigation](#9-bot-detection-and-navigation) | `test_bot_challenge.py`, `test_navigation.py` | pure Python / routed browser | 9 |
| [10. Security: secrets in traces](#10-security-secrets-in-traces) | `test_tracing.py` | headless browser | 4 |
| [11. Utilities and reporting](#11-utilities-and-reporting) | `test_urls.py`, `test_attachments.py` | pure Python | 4 |

```bash
pytest -m smoke        # group 1
pytest -m e2e          # group 2
pytest tests/unit      # groups 3–11 (offline, no eBay)
```

The data-driven tests (groups 1 and 2) run once per row of [data/search_cases.yaml](../data/search_cases.yaml). Today there are two rows: `shoes-under-220` (shoes, max 220, limit 5) and `usb-c-cable-under-15` (usb c cable, max 15, limit 3).

---

## 1. Smoke tests (live eBay)

Fast checks that the site is reachable and not blocking us. Marker: `smoke`.

| Test | What it checks | Expected result |
|---|---|---|
| `test_ebay_home_page_opens` | Opening the eBay home page through `HomePage.open()`. | The page title matches the eBay home title. If eBay shows a bot-check page ("Error Page", "Pardon Our Interruption"), the test fails with `BotChallengeError` and a screenshot. |
| `test_session_is_ready` | The `user_session` fixture: guest by default, signed in when `EBAY_GUEST=false`. | `user_session.guest` matches the setting, and the header shows "signed in" exactly when the session is not a guest. |
| `test_search_results_page_opens` **(×2, per data row)** | After landing on the home page, opening the search results URL for the row's query. | The results page title contains the query text (case-insensitive). |

## 2. E2E scenario tests (live eBay)

The assignment's business flow, step by step and then end to end. Marker: `e2e`. Each runs once per data row.

| Test | What it checks | Expected result |
|---|---|---|
| `test_search_items_by_name_under_price` **(×2)** | Spec 5.2: search by name, filter by max price, collect items via XPath across result pages. | At least 1 item and at most `limit`. URLs are unique, every URL is an `/itm/` link, and every price (the upper bound for a range) is ≤ `max_price`. |
| `test_add_items_to_cart` **(×2)** | Spec 5.3: open each found item, pick random variants if needed, add it to the cart. | Every found URL is added, in order. The header cart badge equals the number of items. The browser is back on the search page, and no item tabs are left open. |
| `test_cart_total_not_exceeds_budget` **(×2)** | Spec 5.5, the full scenario: search → add to cart → open cart → check the total. Severity: critical. | Cart total ≤ `budget_per_item × items added`, and the cart has exactly one line per added item. On failure: a `CartBudgetExceededError` with the actual total vs. the budget, plus a screenshot of the cart. |

## 3. Search result parsing and filtering

Checks the XPath locators against markup copied from a live eBay results page, and the rules that decide which items count.

**`test_search_results_page.py`** (local HTML in headless Chromium)

| Test | What it checks | Expected result |
|---|---|---|
| `test_only_real_listings_before_the_fewer_words_divider` | Which cards are collected: skips carousels, the "Shop on eBay" placeholder, cards with no listing id, and anything after the "Results matching fewer words" divider. | Exactly listings `101`–`106`, in page order. |
| `test_title_without_hidden_suffix_and_clean_url` | Reading title, URL and price from a plain card. | Title is `"Plain shoe"` (no hidden "Opens in a new window" text), URL has no tracking query (`https://www.ebay.com/itm/101`), price is ILS 138.31, not auction-only. |
| `test_range_split_over_spans_is_read_as_range` | A price range that eBay splits over three `<span>`s. | `Price(81.50 → 110.86, ILS)`. |
| `test_crossed_out_price_is_ignored` | A sale card that also shows the old, crossed-out price. | Only the sale price is read: ILS 139.66. |
| `test_auction_only_is_flagged` | A card that is an auction ("0 bids") with no Buy It Now. | `auction_only is True`. |
| `test_auction_with_buy_it_now_uses_the_higher_price` | An auction card that also has a Buy It Now price. | Not auction-only, and the price used is the Buy It Now price (101.93). |
| `test_card_without_price_has_none` | A card with no price row. | `price is None`. |

**`test_search_service.py`** (no browser)

| Test | What it checks | Expected result |
|---|---|---|
| `test_keeps_items_at_or_below_max_and_stops_at_wanted` | The match filter with prices around the max (219.99, 220.00, …). | Items priced ≤ max are kept (220.00 is included), and collection stops at `wanted` (3). |
| `test_skips_expensive_auction_only_unpriced_and_duplicates` | Filtering out the wrong kinds of cards. | Skipped: over max, a range whose upper bound is over max, auction-only, unpriced, and already-seen URLs. Only `ok` is kept, and its URL is added to the seen set. |
| `test_limit_must_be_positive` | `find_items_under_price` with `limit=0`. | `ValueError("limit must be at least 1")`. |

## 4. Cart: add-to-cart flow and budget check

**`test_cart_service.py`, add-to-cart flow** (stubbed pages, no browser)

| Test | What it checks | Expected result |
|---|---|---|
| `test_retries_rejected_variants_on_a_fresh_page` | eBay rejects the variant choice twice ("Please select a Size"). | The item page is reloaded and retried. It succeeds on the 3rd try, and the chosen variant is recorded. |
| `test_gives_up_after_variant_attempts_with_the_last_error` | Variant selection keeps failing past `variant_attempts` (3). | Stops after 3 tries and raises the **last** error. Also takes a `cart_item_1_failed` screenshot, closes the item tab, and returns to the search tab. |
| `test_other_add_to_cart_errors_are_not_retried` | A non-variant failure (no "Add to cart" button). | `AddToCartError` after one try, and the item tab is closed. |
| `test_every_item_tab_is_closed_and_the_cart_count_carries_over` | Adding 3 items when the cart already has 2. | Waits for the badge to go above 2, then 3, then 4. Counts recorded are 3, 4, 5. All item tabs are closed, there is one screenshot per item, and the search tab is brought back each time. |
| `test_title_and_price_are_read_before_the_click` | The order of steps on the item page. | select variants → keep quantity at 1 → read title → read price → click add (the cart page may replace the item page after the click). |

**`test_cart_service.py`, budget assertion (spec 5.4)**

| Test | What it checks | Expected result |
|---|---|---|
| `test_total_within_budget_passes_with_evidence` | Total 600 against a budget of 220 × 3 = 660. | Passes. The cart is opened once, a full-page `cart_page` screenshot is taken, the trace gets a "Cart page" group, and the attached report shows `Budget: 220 per item x 3 items = 660.00` and `Result: OK`. |
| `test_total_equal_to_budget_passes` | Total exactly equal to the budget (0.3 vs 0.1 × 3, a float-rounding trap). | Passes, because the comparison is done in cents. |
| `test_total_above_budget_fails_with_actual_vs_budget` | Total 675.50 against a budget of 660. | `CartBudgetExceededError` (a subclass of `AssertionError`, so pytest reports a failure, not an error) with the message `Cart items ILS 675.50 is above the budget 660.00 (220 per item x 3 items), over by 15.50`. The report says `ABOVE BUDGET`, and the screenshot is taken before the failure. |
| `test_total_line_comes_from_the_profile` | `cart.total_line: subtotal` (items + shipping) instead of `items`. | Uses the subtotal (700), so the check fails with `Cart subtotal ILS 700.00 …`. |
| `test_no_trace_group_when_tracing_is_off` | `trace: off`. | Passes without calling the trace group APIs. |
| `test_negative_budget_is_rejected` | Budget of −1. | `ValueError("must not be negative")`. |
| `test_cart_check_report_lists_every_line` | The text of the attached cart report. | One numbered line per cart item, e.g. `1. 1 x US $16.25 (ILS 59.37) \| Tee`. |

**`test_cart_page.py`** (local HTML copied from the live cart page)

| Test | What it checks | Expected result |
|---|---|---|
| `test_reads_the_items_row_and_the_subtotal_row` | Reading the order-summary rows. | `items` = ILS 223.20 and `subtotal` = ILS 253.20. |
| `test_lines_keep_both_prices_and_default_to_one_unit` | Reading cart line items, including one with no quantity box. | Two `CartLine`s. The converted price is kept (`US $68.99 (ILS 210.70)`), and quantity defaults to 1. |
| `test_thousands_separator_in_the_total` | A total of `ILS 1,234.50`. | 1234.50. |
| `test_unreadable_total_raises` **(×2)** | A total of `-`, or two prices in one cell. | `CartReadError` that names the `items` row. |

## 5. Variant selection (size / color)

**`test_variant_selector.py`**: eBay's variant listbox markup, plus a small script that acts like eBay's (open on click, out-of-stock sizes disappear after a color is picked).

| Test | What it checks | Expected result |
|---|---|---|
| `test_page_without_variants` | A listing with no variant pickers. | `has_variants()` is False and no choices are made. |
| `test_never_picks_an_out_of_stock_value` **(×10 seeds)** | One option is disabled (out of stock). | Always picks the in-stock option (`iPhone 15 Pro`), for every random seed. |
| `test_reads_each_dimension_after_the_previous_pick` **(×10 seeds)** | Color picked first, which removes some sizes. | Always `Color=Red, Size=L`. The size list is read **after** the color pick, and the buttons show "Red" and "L". |
| `test_same_seed_gives_the_same_choices` | Same `RANDOM_SEED` twice on the same page. | Identical choices (reproducible runs). |
| `test_dimension_with_nothing_in_stock_fails_clearly` | All sizes are out of stock. | `VariantSelectionError("No available value for 'Size'")`. |
| `test_missing_values_lists_the_flagged_dimensions` | eBay shows "Please select a Size" after a click. | `missing_values()` returns `["Size"]`. |

## 6. Price parsing

**`test_price_parser.py`**: turns eBay price text into `Price(low, high, currency)`.

| Test | What it checks | Expected result |
|---|---|---|
| `test_single_prices` **(×8)** | `$19.99`, `US $1,234.56`, `ILS 2,458.88`, `£7`, `C $15.00`, `EUR 1.234,50`, `12,50 €`, whitespace-padded `$ 220.00`. | Correct amount and currency (USD/ILS/GBP/CAD/EUR), in both US and European number formats. |
| `test_ranges_keep_both_bounds` **(×4)** | `$10.00 to $25.00`, `ILS 81.50 to ILS 110.86`, `$5.99 - $12.00`, a reversed `$30 TO $20`. | `low`/`high` are both kept and in order, and `is_range` is True. |
| `test_free_is_zero` **(×3)** | `Free`, `FREE`, `Free shipping`. | `Price(0, 0)`. |
| `test_missing_price_is_none` **(×5)** | `None`, empty, whitespace, `See price`, `Price not available`. | `None` (no price, not an error). |
| `test_ambiguous_text_raises` **(×3)** | Two prices with no "to" (sale + old price), a three-part range, `$1.2.3`. | `PriceParseError`. It refuses to guess. |
| `test_parse_amount_conventions` **(×7)** | `15`, `1,234`, `1,234,567.89`, `1.234.567,89`, `0.99`, `12,5`, `220.`. | The right number for each thousands/decimal style. |
| `test_detect_currency` **(×6)** | `AU $3`, `₪50`, `12.00`, `CAD $15.00`, `HKD $20.00`, `US $5`. | AUD, ILS, `None`, CAD, HKD, USD. |
| `test_str_is_readable` | Printing a `Price`. | `ILS 81.50 to 110.86` and `1,234.50`. |

## 7. Configuration (profiles and env vars)

**`test_config.py`**: `base.yaml` → `<env>.yaml` → env vars, with strict validation. A real `.env` file is blocked so it cannot affect these tests.

| Test | What it checks | Expected result |
|---|---|---|
| `test_dev_profile_overrides_base` | Loading `dev`. | Headed, `slow_mo` 100, log level DEBUG. `base_url` and timeouts are inherited from base. |
| `test_ci_profile_is_headless_with_longer_timeouts` | Loading `ci`. | Headless, navigation timeout 45 s, artifacts under `reports/`. |
| `test_env_variable_selects_profile` | `ENV=CI`. | The `ci` profile is loaded (case-insensitive). |
| `test_env_variables_override_profile` | `HEADLESS`, `SLOW_MO`, `BASE_URL` set. | Env values win, and the trailing `/` is stripped from the URL. |
| `test_blank_env_variables_do_not_override_profile` **(×10)** | Each override var set to `""` or spaces. | Settings are the same as the profile alone. |
| `test_headless_env_variable_accepts_bool_spellings` **(×4)** | `TRUE`, `1`, `off`, ` no `. | True, True, False, False. |
| `test_headless_env_variable_rejects_typos` | `HEADLESS=tru`. | `ValueError` naming `HEADLESS` and the bad value. |
| `test_blank_env_variable_falls_back_to_dev` | `ENV` is blank. | The `dev` profile. |
| `test_browser_env_variable_overrides_browser_name` | `BROWSER=Firefox`. | `firefox`. |
| `test_invalid_browser_env_variable_is_rejected` | `BROWSER=safari`. | `ValueError("browser.name must be one of …")`. |
| `test_unknown_profile_lists_available_ones` | Profile `staging`. | `ValueError` that lists `ci, dev`. `base` is not a selectable profile. |
| `test_data_file_path_is_resolved_from_project_root` | The data file path. | An absolute path: `<project>/data/search_cases.yaml`. |
| `test_guest_login_is_the_default` | Default auth. | Guest, with no username. |
| `test_real_login_reads_credentials_from_env` | `EBAY_GUEST=false` and credentials set. | Credentials are loaded, and the password does **not** appear in `repr(settings)`. |
| `test_real_login_without_credentials_is_rejected` **(×2)** | Real login with a blank username or a blank password. | `ValueError("needs EBAY_USERNAME and EBAY_PASSWORD")`. |
| `test_guest_env_variable_rejects_typos` | `EBAY_GUEST=flase`. | `ValueError` that names `EBAY_GUEST`. |
| `test_profile_booleans_must_be_real_yaml_booleans` **(×3)** | YAML `"false"`, `0`, `'yes'` used for boolean keys. | `ValueError("<key> must be true or false")`. A quoted "false" never quietly means True. |
| `test_search_page_limit_comes_from_profile` | `search.max_pages`. | 5. |
| `test_search_page_limit_must_be_a_positive_integer` **(×4)** | `0`, `-1`, `yes`, `'3'`. | `ValueError("search.max_pages must be a positive integer")`. |
| `test_cart_defaults_come_from_profile` | Cart defaults. | `random_seed=None`, `variant_attempts=3`, `total_line="items"`. |
| `test_random_seed_env_variable_overrides_profile` | `RANDOM_SEED=1234`. | 1234. |
| `test_random_seed_env_variable_must_be_an_integer` | `RANDOM_SEED=abc`. | `ValueError`. |
| `test_cart_settings_are_validated` **(×3)** | A bad `random_seed`, `variant_attempts: 0`, `total_line: total`. | `ValueError` with a specific message for each. |
| `test_trace_env_variable_overrides_profile` | `TRACE=ON`. | `on`. |
| `test_trace_env_variable_is_validated` | `TRACE=always`. | `ValueError("artifacts.trace must be one of …")`. |

## 8. Test data loading (data-driven cases)

**`test_data_loader.py`**: validates `data/search_cases.yaml` / `.json` into `SearchCase` rows at collection time.

| Test | What it checks | Expected result |
|---|---|---|
| `test_project_data_file_is_valid` | The real project data file. | Loads, and contains `shoes-under-220` (shoes, 220, limit 5). |
| `test_optional_fields_get_defaults` | A row with only `query` + `max_price`. | Query trimmed, default `limit`, `budget` = `max_price`, generated id `usb_c_cable-under-15`. |
| `test_budget_per_item_overrides_max_price` | `budget_per_item: 1`. | `budget == 1.0`. |
| `test_json_file_is_accepted` | The same data as JSON. | The same `SearchCase` as from YAML. |
| `test_invalid_row_is_rejected_with_its_position` **(×18)** | Missing or blank query, missing/string/zero/inf/NaN `max_price`, bad `limit` (0, 2.5, yes), bad `budget_per_item`, bad `id` types, a typo key (`max_pirce`), a row that is not a mapping. | `ValueError` that names the file, the row number (`case #2`) and the exact problem. |
| `test_missing_or_empty_cases_list_is_rejected` **(×3)** | Empty file, `cases: []`, a list without the `cases:` key. | `ValueError("expected a non-empty 'cases:' list")`. |
| `test_duplicate_ids_are_rejected` | Two rows that generate the same id. | `ValueError` that names the duplicate id and both row numbers. |

## 9. Bot detection and navigation

**`test_bot_challenge.py`** (pure logic on title + URL)

| Test | What it checks | Expected result |
|---|---|---|
| `test_bot_check_pages_are_detected` **(×4)** | "Pardon Our Interruption…", "Error Page \| eBay", "Security Measure \| eBay", a `/splashui/challenge` URL. | Each is flagged as a bot check (a reason is returned). |
| `test_normal_pages_are_not_flagged` **(×3)** | The home page, the sign-in page, an item called "Error Page T-Shirt". | Not flagged. Only the title **prefix** counts. |

**`test_navigation.py`** (headless browser, pages served by a fake route)

| Test | What it checks | Expected result |
|---|---|---|
| `test_waits_for_the_new_page_even_if_the_current_url_already_matches` | `expect_navigation` when the click navigates later, and the current URL already matches the target pattern. | Waits for the **new** page (`_nkw=second`) instead of returning at once on the old URL. |
| `test_bot_check_redirect_ends_the_wait_with_a_clear_error` | The navigation lands on a bot-check page. | `BotChallengeError("Pardon Our Interruption")` right away, not a timeout. |

## 10. Security: secrets in traces

**`test_tracing.py`**: Playwright traces store `fill()` values in plain text and get attached to reports. `tracing_paused` must keep passwords out.

| Test | What it checks | Expected result |
|---|---|---|
| `test_unpaused_trace_records_the_password` | Control: typing a password **without** pausing. | The secret **is** in the trace zip, which proves the leak check below works. |
| `test_paused_trace_omits_the_password_and_keeps_recording` | Typing the password inside `tracing_paused`. | The secret is **not** in the trace, and later actions ("signed in") are still recorded. |
| `test_tracing_resumes_when_the_block_fails` | An exception inside the paused block. | Tracing is resumed, and the trace zip is still saved. |
| `test_inactive_tracing_is_left_alone` | Pausing when tracing was never started. | No error. |

## 11. Utilities and reporting

| Test | What it checks | Expected result |
|---|---|---|
| `test_with_query_sets_replaces_and_removes` (`test_urls.py`) | Changing query params on a search URL. | `_udhi` is added, `_sacat` replaced, `_pgn` removed, `_nkw` kept. |
| `test_query_param_missing_is_none` (`test_urls.py`) | Reading a param that is not there. | `None`. |
| `test_without_query_keeps_the_item_path` (`test_urls.py`) | Removing tracking params and the fragment from an item URL. | `https://www.ebay.com/itm/298422393864`. |
| `test_allure_environment_is_a_properties_file` (`test_attachments.py`) | Writing Allure's `environment.properties`. | One `key=value` per line. Spaces in keys and backslashes are escaped (`Base\ URL=…`, `data\\search_cases.yaml`). |
