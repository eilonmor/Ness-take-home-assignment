# Ness-take-home-assignment

E2E scenario on eBay with Playwright + Python: search → filter by price → add to cart → assert the cart total.
The full README (setup, run commands, reports) is written in Stage 9; see [MISSION_PLAN.md](MISSION_PLAN.md).

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
