"""Framework exceptions: failures caused by the site, not by a wrong assertion."""

from __future__ import annotations


class BotChallengeError(RuntimeError):
    """eBay served a captcha / bot-check page instead of the requested content."""


class LoginError(RuntimeError):
    """Sign-in was rejected or stopped at a step the framework cannot automate."""


class AddToCartError(RuntimeError):
    """An item could not be added to the cart (no button, no available variant, eBay error)."""


class VariantSelectionError(AddToCartError):
    """The random variant combination could not be used; another one may work."""


class CartReadError(RuntimeError):
    """The cart page did not show a readable total."""


class CartBudgetExceededError(AssertionError):
    """The cart total is above budget_per_item * items_count (spec 5.4).

    An ``AssertionError``, so pytest reports a failed check, not a broken test.
    """
