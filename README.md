# Ness-take-home-assignment

E2E scenario on eBay with Playwright + Python: search → filter by price → add to cart → assert the cart total.
The full README (setup, run commands, reports) is written in Stage 9; see [MISSION_PLAN.md](MISSION_PLAN.md).

## Limitations

### Login: guest session by default
eBay protects sign-in with captcha and bot checks, so every run starts as a **guest**. The spec allows a guest/stub login, and a guest can search and use the cart.

- The session is prepared by `AuthService` ([services/auth_service.py](services/auth_service.py)), which tests use through the `user_session` fixture. It opens the home page, closes the "Are you shipping to …?" dialog, and checks that the header shows a signed-out visitor.
- Real sign-in is opt-in: set `EBAY_GUEST=false` plus `EBAY_USERNAME` / `EBAY_PASSWORD` in `.env` (template: [.env.example](.env.example)). It is implemented but **not verified end to end**. If eBay asks for a captcha, 2FA or a passkey, the run stops with a clear `BotChallengeError` / `LoginError`.

### Bot detection
- Headless runs are blocked by eBay ("Error Page" / "Security Measure" captcha). Run headed: the default `dev` profile, or `HEADLESS=false`.
- Many runs in a short time are rate-limited even when headed. The run then fails fast with `eBay served a bot check (...)` and a screenshot. Wait a few minutes before retrying.

Design rationale: [docs/DECISIONS.md](docs/DECISIONS.md) ADR-6.
