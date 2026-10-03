# AI-Generated Code Review: Bugs and Fixes

A static review of an AI-generated Playwright test. The original code is below, then the bugs (most serious first), then the corrected version.

## Original code

```python
from playwright.sync_api import sync_playwright
from selenium import webdriver
import time

def test_search_functionality():
    browser = sync_playwright().start().chromium.launch()
    page = browser.new_page()
    page.goto("https://example.com")

    time.sleep(2)

    search_box = page.locator("#search")
    search_box.fill("playwright testing")

    page.locator(".button").click()

    time.sleep(3)

    results = page.locator(".result-item")

    browser.close()
```

## Main issues

### 1. The test checks nothing

`results` is created but never used. `page.locator()` is lazy: it does not touch the page until you act on it or assert on it. If the search returns nothing or is broken, the test still passes. It gives false confidence, which is worse than having no test.

**Fix:** assert on the results with web-first assertions, which retry until the condition holds or the timeout expires:

```python
results = page.locator(".result-item")
expect(results.first).to_be_visible()
expect(results).not_to_have_count(0)
```

### 2. `time.sleep()` instead of waiting for a condition

Playwright already waits for an element to be attached, visible, enabled and stable before `fill()` and `click()`, so `time.sleep(2)` adds nothing. `time.sleep(3)` is a guess: on a slow run it is too short and the test fails at random (flaky), and on a fast run it wastes 3 seconds every time.

**Fix:** remove both sleeps. Rely on auto-waiting for actions, and use `expect(...)` for the outcome. It waits only as long as needed and fails with a clear message if the condition is never met.

### 3. Resources leak

- `sync_playwright().start()` starts the Playwright driver process, but the returned object is thrown away, so `.stop()` can never be called. The driver process stays running.
- `browser.close()` is not in a `finally` block. If any step raises (for example, a selector timeout), the browser is never closed. In a large suite these leftover processes pile up and slow down or crash the machine/CI agent.

**Fix:** `with sync_playwright() as p:` (stops the driver on exit) plus `try/finally` around the browser, or use the pytest-playwright `page` fixture, which handles both.

### 4. The `.button` selector is too generic

If the page has more than one element with the `button` class, Playwright's strict mode raises an error on `click()`. Even if only one matches today, the test breaks as soon as someone changes the CSS classes, and it may click the wrong button.

**Fix:** use a user-facing locator that describes intent, such as `page.get_by_role("button", name="Search")`, or a dedicated `data-testid` attribute (`page.get_by_test_id("search-submit")`).

## Minor issues

### 5. Unused `selenium` import

`from selenium import webdriver` is never used. It adds a dependency for nothing (the test fails with `ModuleNotFoundError` on a machine without Selenium) and mixes two automation frameworks in one file, which is confusing for readers.

**Fix:** delete the import.

### 6. The target page does not match the selectors, and the URL is hard-coded

`https://example.com` has no `#search` input. If this is not just a placeholder, `fill()` waits for the default 30 seconds and then fails. The URL is also hard-coded, so the test cannot run against another environment (dev/staging/prod) without editing code.

**Fix:** point the test at the real application under test, and take the base URL from configuration (`pytest --base-url ...` with pytest-playwright, or a config file / environment variable), navigating with a relative path such as `page.goto("/")`.

### 7. No pytest-playwright fixtures

The `page` fixture from pytest-playwright handles browser launch, context isolation and cleanup, and lets you choose options from the command line (`--headed`, `--browser firefox`, `--slowmo`, `--base-url`, `--tracing`) without changing code.

### 8. The browser is used without an explicit context

`browser.new_page()` creates an implicit context. Creating one explicitly with `browser.new_context()` makes isolation (cookies, storage) visible in the code and lets you set options such as viewport, locale and `base_url`.

## Corrected code

```python
from playwright.sync_api import Page, expect


def test_search_functionality(page: Page):
    page.goto("/")  # base URL from config: pytest --base-url https://<app-under-test>

    page.locator("#search").fill("playwright testing")
    page.get_by_role("button", name="Search").click()

    results = page.locator(".result-item")
    expect(results.first).to_be_visible()
    expect(results).not_to_have_count(0)
    expect(results.first).to_contain_text("Playwright", ignore_case=True)
```

## Summary

| # | Issue | Severity | Fix |
|---|---|---|---|
| 1 | No assertion: the test always passes | High | `expect(...)` on the results |
| 2 | `time.sleep()` hard waits | High | Auto-waiting + `expect(...)` |
| 3 | Driver and browser leak | High | `with sync_playwright()` + `try/finally`, or the `page` fixture |
| 4 | Generic `.button` selector | Medium | `get_by_role("button", name="Search")` / `data-testid` |
| 5 | Unused `selenium` import | Low | Remove it |
| 6 | Wrong / hard-coded URL | Low | Real target, base URL from config |
| 7 | No pytest-playwright fixtures | Low | Use the `page` fixture |
| 8 | Implicit browser context | Low | `browser.new_context(...)` |
