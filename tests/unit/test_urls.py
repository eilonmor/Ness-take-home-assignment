from utils.urls import query_param, with_query, without_query

SEARCH = "https://www.ebay.com/sch/i.html?_nkw=shoes&_sacat=0&_pgn=3"


def test_with_query_sets_replaces_and_removes() -> None:
    url = with_query(SEARCH, _udhi="220", _pgn=None, _sacat="11450")

    assert query_param(url, "_udhi") == "220"
    assert query_param(url, "_sacat") == "11450"
    assert query_param(url, "_nkw") == "shoes"
    assert query_param(url, "_pgn") is None


def test_query_param_missing_is_none() -> None:
    assert query_param("https://www.ebay.com/", "_pgn") is None


def test_without_query_keeps_the_item_path() -> None:
    url = "https://www.ebay.com/itm/298422393864?_skw=shoes&itmmeta=01M3W&hash=item457b#tab"

    assert without_query(url) == "https://www.ebay.com/itm/298422393864"
