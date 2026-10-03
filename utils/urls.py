"""Small URL helpers for search and item links."""

from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


def with_query(url: str, **params: str | None) -> str:
    """Set (or, with None, remove) query parameters, keeping the others."""
    parts = urlsplit(url)
    query = {key: value for key, value in parse_qsl(parts.query, keep_blank_values=True) if key not in params}
    query.update({key: value for key, value in params.items() if value is not None})
    return urlunsplit(parts._replace(query=urlencode(query)))


def query_param(url: str, name: str) -> str | None:
    return dict(parse_qsl(urlsplit(url).query)).get(name)


def without_query(url: str) -> str:
    """Drop query and fragment: eBay item links carry per-search tracking params."""
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))
