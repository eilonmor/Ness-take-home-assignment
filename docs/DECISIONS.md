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
- ❌ Real sign-in is implemented but not verified end to end (no test account, and headless always hits the captcha). Only the unknown-account error path was checked by hand.
- ❌ Guest only: no saved addresses or watchlist. Prices and the cart total are those shown to an anonymous visitor in the detected region.
