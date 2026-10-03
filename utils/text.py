"""Text comparison helpers for texts eBay rewrites (page titles, headings)."""

from __future__ import annotations

import unicodedata


def fold(text: str) -> str:
    """Case- and accent-insensitive form: eBay titles a "pokémon cards" search "Pokemon Cards for sale"."""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(char for char in decomposed if not unicodedata.combining(char)).casefold()
