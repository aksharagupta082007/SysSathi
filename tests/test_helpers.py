"""Test helpers re-exporting grounding functions for backward compatibility."""

from __future__ import annotations

from syssathi.grounding import (
    collect_allowed_numbers,
    extract_numbers_from_text,
    normalize_digits,
    verify_reply_numbers,
)

__all__ = [
    "collect_allowed_numbers",
    "extract_numbers_from_text",
    "normalize_digits",
    "verify_reply_numbers",
]
