from pathlib import Path

import pytest

from core.config import PROJECT_ROOT
from core.constants import DEFAULT_SEARCH_LIMIT as DEFAULT_LIMIT
from core.data_loader import SearchCase, load_search_cases


def write_cases(tmp_path: Path, content: str) -> Path:
    path = tmp_path / "cases.yaml"
    path.write_text(content, encoding="utf-8")
    return path


def test_project_data_file_is_valid() -> None:
    cases = load_search_cases(PROJECT_ROOT / "data" / "search_cases.yaml")

    assert SearchCase(id="shoes-under-220", query="shoes", max_price=220.0, limit=5) in cases


def test_optional_fields_get_defaults(tmp_path: Path) -> None:
    [case] = load_search_cases(write_cases(tmp_path, "cases:\n  - {query: ' usb c cable ', max_price: 15}\n"))

    assert case.query == "usb c cable"
    assert case.limit == DEFAULT_LIMIT
    assert case.budget == 15.0
    assert case.id == "usb_c_cable-under-15"


def test_budget_per_item_overrides_max_price(tmp_path: Path) -> None:
    [case] = load_search_cases(write_cases(tmp_path, "cases:\n  - {query: shoes, max_price: 220, budget_per_item: 1}\n"))

    assert case.budget == 1.0


def test_json_file_is_accepted(tmp_path: Path) -> None:
    path = tmp_path / "cases.json"
    path.write_text('{"cases": [{"query": "shoes", "max_price": 99.5, "limit": 2}]}', encoding="utf-8")

    assert load_search_cases(path) == [SearchCase(id="shoes-under-99.5", query="shoes", max_price=99.5, limit=2)]


@pytest.mark.parametrize(
    ("row", "error"),
    [
        ("{max_price: 10}", "'query' must be a non-empty string"),
        ("{query: '  ', max_price: 10}", "'query' must be a non-empty string"),
        ("{query: shoes}", "'max_price' must be a positive number, got None"),
        ("{query: shoes, max_price: '220'}", "'max_price' must be a positive number"),
        ("{query: shoes, max_price: 0}", "'max_price' must be a positive number"),
        ("{query: shoes, max_price: 10, limit: 0}", "'limit' must be a positive integer"),
        ("{query: shoes, max_price: 10, limit: 2.5}", "'limit' must be a positive integer"),
        ("{query: shoes, max_price: 10, limit: yes}", "'limit' must be a positive integer"),
        ("{query: shoes, max_price: 10, budget_per_item: -1}", "'budget_per_item' must be a positive number"),
        ("{query: shoes, max_price: .inf}", "'max_price' must be a positive number, got inf"),
        ("{query: shoes, max_price: .nan}", "'max_price' must be a positive number, got nan"),
        ("{query: shoes, max_price: 10, budget_per_item: .inf}", "'budget_per_item' must be a positive number"),
        ("{id: 123, query: shoes, max_price: 10}", "'id' must be a non-empty string, got 123"),
        ("{id: false, query: shoes, max_price: 10}", "'id' must be a non-empty string, got False"),
        ("{id: '  ', query: shoes, max_price: 10}", "'id' must be a non-empty string"),
        ("{id: [a], query: shoes, max_price: 10}", "'id' must be a non-empty string"),
        ("{query: shoes, max_pirce: 10}", r"unknown key\(s\) \['max_pirce'\]"),
        ("shoes", "expected a mapping, got str"),
    ],
)
def test_invalid_row_is_rejected_with_its_position(tmp_path: Path, row: str, error: str) -> None:
    path = write_cases(tmp_path, f"cases:\n  - {{query: ok, max_price: 1}}\n  - {row}\n")

    with pytest.raises(ValueError, match=f"cases.yaml case #2: {error}"):
        load_search_cases(path)


@pytest.mark.parametrize("content", ["", "cases: []\n", "- {query: shoes, max_price: 10}\n"])
def test_missing_or_empty_cases_list_is_rejected(tmp_path: Path, content: str) -> None:
    with pytest.raises(ValueError, match="expected a non-empty 'cases:' list"):
        load_search_cases(write_cases(tmp_path, content))


def test_duplicate_ids_are_rejected(tmp_path: Path) -> None:
    path = write_cases(tmp_path, "cases:\n  - {query: shoes, max_price: 10}\n  - {query: shoes, max_price: 10}\n")

    with pytest.raises(ValueError, match=r"case #2: duplicate case id 'shoes-under-10' \(first used by case #1\)"):
        load_search_cases(path)
