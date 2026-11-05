"""Router — keyword fast path vs Evon route (Addendum A4: whole-word matching)."""

from __future__ import annotations

import re
import unicodedata

from syssathi.host.config import SLOWNESS_KEYWORDS


def _normalize(text: str) -> str:
    """Lowercase, strip punctuation and extra whitespace."""
    text = text.lower()
    # Replace punctuation with spaces (keep letters, digits, whitespace)
    text = re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _build_pattern(keywords: list[str]) -> re.Pattern[str]:
    """Build a single regex that matches any keyword as a whole word/phrase.

    Addendum A4: match whole words and whole phrases on the normalized text.
    Never match a keyword inside a longer word.
    """
    # Sort longest first so multi-word phrases match before their parts
    sorted_kw = sorted(keywords, key=len, reverse=True)
    # Escape each keyword and join with alternation
    escaped = [re.escape(kw.lower()) for kw in sorted_kw]
    # Use word boundaries for whole-word matching
    pattern = r"\b(?:" + "|".join(escaped) + r")\b"
    return re.compile(pattern, re.UNICODE)


# Pre-compiled pattern from the default keyword list
_KEYWORD_RE: re.Pattern[str] = _build_pattern(SLOWNESS_KEYWORDS)


def route(text: str, keywords: list[str] | None = None) -> str:
    """Return 'fast' if text matches a slowness keyword, else 'evon'.

    Args:
        text: raw user utterance.
        keywords: override the default keyword list (for testing).
    """
    normalized = _normalize(text)

    if keywords is not None:
        pattern = _build_pattern(keywords)
    else:
        pattern = _KEYWORD_RE

    if pattern.search(normalized):
        return "fast"
    return "evon"

