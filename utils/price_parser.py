"""Turn price labels as eBay shows them into numbers.

    "$1,234.56"                 -> Price(1234.56, 1234.56, "USD")
    "ILS 81.50 to ILS 110.86"   -> Price(81.50, 110.86, "ILS")   (check ``high`` against a max)
    "EUR 1.234,50"              -> Price(1234.50, 1234.50, "EUR")
    "Free"                      -> Price(0.0, 0.0)
    "" / None                   -> None (no price shown)

Text that has digits but cannot be read unambiguously (e.g. two prices with
no range separator) raises ``PriceParseError`` instead of guessing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Longest first: "US $" must win over "$".
CURRENCY_SYMBOLS = (
    ("US $", "USD"),
    ("C $", "CAD"),
    ("AU $", "AUD"),
    ("$", "USD"),
    ("£", "GBP"),
    ("€", "EUR"),
    ("₪", "ILS"),
)
_CURRENCY_CODE = re.compile(r"\b([A-Z]{3})\b")
_AMOUNT = re.compile(r"\d[\d.,]*")
_RANGE_SEPARATOR = re.compile(r"\s+(?:to|-|–)\s+", re.IGNORECASE)


class PriceParseError(ValueError):
    """The label contains digits but no single, unambiguous price or range."""


@dataclass(frozen=True)
class Price:
    low: float
    high: float
    currency: str | None = None

    @property
    def is_range(self) -> bool:
        return self.low != self.high

    def __str__(self) -> str:
        amount = f"{self.low:,.2f}" if not self.is_range else f"{self.low:,.2f} to {self.high:,.2f}"
        return f"{self.currency} {amount}" if self.currency else amount


def parse_price(text: str | None) -> Price | None:
    """Parse one price or price range; None when no price is shown."""
    cleaned = " ".join((text or "").split())
    if not cleaned:
        return None
    if not any(char.isdigit() for char in cleaned):
        if "free" in cleaned.lower():
            return Price(0.0, 0.0)
        return None

    parts = _RANGE_SEPARATOR.split(cleaned)
    if len(parts) > 2:
        raise PriceParseError(f"More than two prices in a range: {text!r}")
    amounts = [_single_amount(part, text) for part in parts]
    return Price(low=min(amounts), high=max(amounts), currency=detect_currency(cleaned))


def parse_amount(text: str) -> float:
    """One number written with any thousands/decimal convention: "2,458.88", "1.234,50", "15"."""
    amount = text.strip().rstrip(".,")
    if not amount or not amount[0].isdigit():
        raise PriceParseError(f"Not a number: {text!r}")

    has_comma, has_dot = "," in amount, "." in amount
    if has_comma and has_dot:
        # The separator that comes last is the decimal one.
        decimal, thousands = (",", ".") if amount.rfind(",") > amount.rfind(".") else (".", ",")
        amount = amount.replace(thousands, "").replace(decimal, ".")
    elif has_comma or has_dot:
        separator = "," if has_comma else "."
        # "1,234" / "1.234.567": groups of three digits are thousands, otherwise it is a decimal point.
        if re.fullmatch(rf"\d{{1,3}}(?:{re.escape(separator)}\d{{3}})+", amount):
            amount = amount.replace(separator, "")
        elif amount.count(separator) == 1:
            amount = amount.replace(separator, ".")
        else:
            raise PriceParseError(f"Ambiguous number: {text!r}")
    return float(amount)


def detect_currency(text: str) -> str | None:
    """An explicit code wins over a symbol: "CAD $15.00" is CAD, not USD."""
    match = _CURRENCY_CODE.search(text)
    if match:
        return match.group(1)
    for symbol, code in CURRENCY_SYMBOLS:
        if symbol in text:
            return code
    return None


def _single_amount(part: str, original: str | None) -> float:
    amounts = _AMOUNT.findall(part)
    if len(amounts) != 1:
        raise PriceParseError(f"Expected one price in {part!r} (from {original!r}), found {len(amounts)}")
    return parse_amount(amounts[0])
