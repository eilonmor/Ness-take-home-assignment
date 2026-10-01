"""Load data-driven test cases from YAML/JSON files in ``data/``.

Each row is validated up front, so a typo in the data file fails the run at
collection time with the file name and row number - not halfway through a
browser session.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any

import yaml

from utils.files import safe_filename

DEFAULT_LIMIT = 5


@dataclass(frozen=True)
class SearchCase:
    """One search → add to cart → assert total scenario."""

    id: str
    query: str
    max_price: float
    limit: int = DEFAULT_LIMIT
    budget_per_item: float | None = None

    @property
    def budget(self) -> float:
        """Per-item budget for the cart check; defaults to ``max_price``."""
        return self.max_price if self.budget_per_item is None else self.budget_per_item


def load_search_cases(path: Path) -> list[SearchCase]:
    """Read ``cases:`` from a YAML (or JSON) file into validated SearchCase rows."""
    with path.open(encoding="utf-8") as file:
        raw = yaml.safe_load(file) or {}

    rows = raw.get("cases") if isinstance(raw, dict) else None
    if not isinstance(rows, list) or not rows:
        raise ValueError(f"{path.name}: expected a non-empty 'cases:' list")

    cases = [_parse_case(row, f"{path.name} case #{index}") for index, row in enumerate(rows, start=1)]

    seen: set[str] = set()
    for case in cases:
        if case.id in seen:
            raise ValueError(f"{path.name}: duplicate case id '{case.id}'")
        seen.add(case.id)
    return cases


def _parse_case(row: Any, where: str) -> SearchCase:
    if not isinstance(row, dict):
        raise ValueError(f"{where}: expected a mapping, got {type(row).__name__}")

    unknown = set(row) - {field.name for field in fields(SearchCase)}
    if unknown:
        raise ValueError(f"{where}: unknown key(s) {sorted(unknown)}")

    query = row.get("query")
    if not isinstance(query, str) or not query.strip():
        raise ValueError(f"{where}: 'query' must be a non-empty string")
    query = query.strip()

    max_price = _positive_number(row.get("max_price"), "max_price", where)
    limit = row.get("limit", DEFAULT_LIMIT)
    # bool is a subclass of int: reject `limit: yes`.
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        raise ValueError(f"{where}: 'limit' must be a positive integer, got {limit!r}")

    budget_per_item = row.get("budget_per_item")
    if budget_per_item is not None:
        budget_per_item = _positive_number(budget_per_item, "budget_per_item", where)

    case_id = str(row.get("id") or safe_filename(f"{query}-under-{max_price:g}"))
    return SearchCase(id=case_id, query=query, max_price=max_price, limit=limit, budget_per_item=budget_per_item)


def _positive_number(value: Any, name: str, where: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        raise ValueError(f"{where}: '{name}' must be a positive number, got {value!r}")
    return float(value)
