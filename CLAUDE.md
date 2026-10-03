# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Take-home assignment: Playwright + Python E2E scenario against live eBay (search under a price → add items to cart → assert cart total ≤ budget × count), built as a self-developed Page Object Model with Allure reports. [MISSION_PLAN.md](MISSION_PLAN.md) is the spec and stage tracker (stages 0–4 done, 5+ pending) — check it before starting work and tick off items when a stage lands. Non-obvious design choices are recorded as ADRs in [docs/DECISIONS.md](docs/DECISIONS.md); add a new ADR (Context → Decision → Alternatives → Consequences) for any comparable decision.

## Commands

Requires Python 3.11+ (`typing.Self`). A venv lives in `.venv/`.

```bash
pip install -r requirements.txt
python -m playwright install chromium

pytest                                   # all tests, profile from $ENV / .env, default "dev"
pytest --env ci                          # pick profile config/ci.yaml (or ENV=ci pytest)
pytest tests/unit                        # offline unit tests (no eBay)
pytest -m smoke                          # markers: smoke, e2e
pytest tests/unit/test_config.py::test_name
pytest "tests/e2e/test_search_smoke.py::test_search_results_page_opens[shoes-under-220]"
pytest --collect-only                    # also validates profile, .env and data file

allure serve reports/allure-results      # needs the separate Allure CLI; pytest.ini always writes here (--clean-alluredir)
playwright show-trace reports/traces/<file>.zip
```

`pytest-playwright` is intentionally **not** used (ADR-1): `--headed`, `--browser`, `--slowmo` don't exist. Use env overrides instead: `HEADLESS=false`, `BROWSER=firefox`, `SLOW_MO=250`, `BASE_URL=...`.

## Architecture

Layers (each depends only on those below): `tests/` → `services/` (business flows, e.g. `AuthService`) → `pages/` → `components/` (reusable UI parts like `Header`) → `core/` + `utils/`. Tests never use raw selectors; page objects and components both subclass `core.base_page.BasePage` and get `(page, settings)` in the constructor.

**Settings** ([core/config.py](core/config.py)): `config/base.yaml` → `config/<ENV>.yaml` → env vars, deep-merged into frozen dataclasses. Profile chosen by `--env`, else `ENV`, else `dev` (headed — needed against eBay). Validation is strict on purpose (quoted `"false"` in YAML is rejected, unknown bool strings raise). Credentials (`EBAY_USERNAME`/`EBAY_PASSWORD`) come only from the environment/`.env`, never profiles; `password` is `repr=False`.

**Fixtures** ([tests/conftest.py](tests/conftest.py)): session-scoped `settings` → `playwright` → `browser`; per-test `context` → `page` (fresh cookies/cart per test, ADR-3). The context sets `base_url`, so navigate with relative paths (`page.goto("/sch/...")`). Context teardown handles failure evidence: full-page screenshots of every open page + trace (`retain-on-failure` by default) saved under `reports/` and attached to Allure. `user_session` fixture runs `AuthService.start_session()` (guest by default) and leaves the page on the home page.

**Data-driven** ([core/data_loader.py](core/data_loader.py)): any test with a `search_case` argument is parametrized by `pytest_generate_tests` from the profile's `data.search_cases` file (default [data/search_cases.yaml](data/search_cases.yaml)), one test per row, test id = row `id`. Rows are validated into frozen `SearchCase` objects at collection time. Settings are cached on `config.stash` so collection and fixtures share one instance.

**Evidence/logging**: use `BasePage.take_screenshot(name)` for step screenshots (auto-attached to Allure) and `self.log` (child of the `ness` logger; output also in `reports/logs/run.log`). Wrap business steps in `allure.step(...)`.

## eBay-specific gotchas

- eBay blocks headless runs ("Error Page | eBay") and rate-limits bursts even when headed. `BasePage.open()` calls `ensure_not_blocked()`, which raises `BotChallengeError` with a screenshot. CAPTCHA solving/bypass is explicitly out of scope — detect and fail, never work around it. Call `ensure_not_blocked()` after any new navigation path too.
- A cold deep link to `/sch/...` gets the bot page; start from the home page (via `user_session`) and search from there.
- The "Are you shipping to …?" modal blocks all clicks and sets the rest of the header `aria-hidden`, so role locators fail while it's open — `Header.dismiss_ship_to_dialog()` handles it; header locators are CSS for this reason.
- Anything that types a secret must run inside `utils.tracing.tracing_paused` (traces store `fill()` values in plain text and get attached to reports); [tests/unit/test_tracing.py](tests/unit/test_tracing.py) guards this.
- The spec requires **XPath** for collecting search result items (MISSION_PLAN §5.2).
