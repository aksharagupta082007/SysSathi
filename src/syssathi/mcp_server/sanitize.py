"""Sanitize machine-sourced strings before they enter prompts or logs."""

from __future__ import annotations

import re

_CONTROL_RE = re.compile(
    r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]"
)
MAX_LEN = 40


def sanitize(text: str) -> str:
    """Clean a machine-sourced string.

    1. Strip control characters (keep space, tab, newline → replaced).
    2. If it looks like a path (contains \\ or /), keep only the final component.
    3. Truncate to 40 characters.
    """
    # Strip control characters
    cleaned = _CONTROL_RE.sub("", text)
    # Replace tabs/newlines with space
    cleaned = cleaned.replace("\t", " ").replace("\n", " ").replace("\r", " ")
    # Extract basename if it looks like a path
    if "\\" in cleaned or "/" in cleaned:
        parts = re.split(r"[/\\]", cleaned)
        cleaned = parts[-1] if parts[-1] else cleaned
    # Truncate
    return cleaned[:MAX_LEN]

