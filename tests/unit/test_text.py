import pytest

from utils.text import fold


@pytest.mark.parametrize(
    ("query", "title"),
    [
        ("pokémon cards", "Pokemon Cards for sale | eBay"),
        ("USB C cable", "Usb C Cable for sale | eBay"),
        ("crème brûlée", "Creme Brulee Torch for sale | eBay"),
    ],
)
def test_query_is_found_in_the_title_eBay_rewrote(query: str, title: str) -> None:
    assert fold(query) in fold(title)


def test_different_letters_still_differ() -> None:
    assert fold("pokémon") != fold("pokemen")
