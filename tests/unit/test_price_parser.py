import pytest

from utils.price_parser import Price, PriceParseError, detect_currency, parse_amount, parse_price


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("$19.99", Price(19.99, 19.99, "USD")),
        ("US $1,234.56", Price(1234.56, 1234.56, "USD")),
        ("ILS 2,458.88", Price(2458.88, 2458.88, "ILS")),
        ("£7", Price(7.0, 7.0, "GBP")),
        ("C $15.00", Price(15.0, 15.0, "CAD")),
        ("EUR 1.234,50", Price(1234.5, 1234.5, "EUR")),
        ("12,50 €", Price(12.5, 12.5, "EUR")),
        ("  $ 220.00\n", Price(220.0, 220.0, "USD")),
    ],
)
def test_single_prices(text: str, expected: Price) -> None:
    assert parse_price(text) == expected


@pytest.mark.parametrize(
    ("text", "low", "high"),
    [
        ("$10.00 to $25.00", 10.0, 25.0),
        # eBay's search cards split a range into three spans; joined they read like this.
        ("ILS 81.50 to ILS 110.86", 81.5, 110.86),
        ("$5.99 - $12.00", 5.99, 12.0),
        ("$30.00 TO $20.00", 20.0, 30.0),
    ],
)
def test_ranges_keep_both_bounds(text: str, low: float, high: float) -> None:
    price = parse_price(text)

    assert price is not None
    assert (price.low, price.high) == (low, high)
    assert price.is_range


@pytest.mark.parametrize("text", ["Free", "FREE", "Free shipping"])
def test_free_is_zero(text: str) -> None:
    assert parse_price(text) == Price(0.0, 0.0)


@pytest.mark.parametrize("text", [None, "", "   ", "See price", "Price not available"])
def test_missing_price_is_none(text: str | None) -> None:
    assert parse_price(text) is None


@pytest.mark.parametrize(
    "text",
    [
        "ILS 139.66 ILS 164.31",  # sale price + crossed-out price read together: which one?
        "$1 to $2 to $3",
        "$1.2.3",
    ],
)
def test_ambiguous_text_raises(text: str) -> None:
    with pytest.raises(PriceParseError):
        parse_price(text)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("15", 15.0),
        ("1,234", 1234.0),
        ("1,234,567.89", 1234567.89),
        ("1.234.567,89", 1234567.89),
        ("0.99", 0.99),
        ("12,5", 12.5),
        ("220.", 220.0),
    ],
)
def test_parse_amount_conventions(text: str, expected: float) -> None:
    assert parse_amount(text) == pytest.approx(expected)


@pytest.mark.parametrize(
    ("text", "currency"),
    [("AU $3", "AUD"), ("₪50", "ILS"), ("12.00", None), ("CAD $15.00", "CAD"), ("HKD $20.00", "HKD"), ("US $5", "USD")],
)
def test_detect_currency(text: str, currency: str | None) -> None:
    assert detect_currency(text) == currency


def test_str_is_readable() -> None:
    assert str(Price(81.5, 110.86, "ILS")) == "ILS 81.50 to 110.86"
    assert str(Price(1234.5, 1234.5)) == "1,234.50"
