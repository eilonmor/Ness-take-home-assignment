"""Framework exceptions: failures caused by the site, not by a wrong assertion."""

from __future__ import annotations


class BotChallengeError(RuntimeError):
    """eBay served a captcha / bot-check page instead of the requested content."""


class LoginError(RuntimeError):
    """Sign-in was rejected or stopped at a step the framework cannot automate."""
