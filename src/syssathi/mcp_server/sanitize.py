"""Sanitize machine-sourced strings before they enter prompts or logs."""

from __future__ import annotations

import re
import unicodedata

_CONTROL_RE = re.compile(
    r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]"
)
MAX_LEN = 40


def sanitize(text: str) -> str:
    """Clean a machine-sourced string.

    1. Strip control characters and Unicode category 'Cf' (bidi overrides, zero-width chars).
    2. Replace tabs/newlines with space.
    3. If it looks like a path (contains \\ or /), keep only the final component.
    4. Truncate to 40 characters.
    """
    # Strip C0/C1 control characters and Unicode format characters (category Cf)
    cleaned = "".join(
        ch for ch in text
        if unicodedata.category(ch) != "Cf" and not _CONTROL_RE.match(ch)
    )
    # Replace tabs/newlines with space
    cleaned = cleaned.replace("\t", " ").replace("\n", " ").replace("\r", " ")
    # Extract basename if it looks like a path
    if "\\" in cleaned or "/" in cleaned:
        parts = re.split(r"[/\\]", cleaned)
        cleaned = parts[-1] if parts[-1] else cleaned
    # Truncate
    return cleaned[:MAX_LEN]

