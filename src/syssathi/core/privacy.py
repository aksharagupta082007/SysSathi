"""Privacy and sensitive data redaction helpers (Phase E §7.4).

Ensures personal paths (e.g. C:\\Users\\<username>\\...) and system usernames
are redacted before leaving the local machine to external models.
"""

from __future__ import annotations

import getpass
import os
import re
from pathlib import Path
from typing import Any

# Detect current local username
try:
    _CURRENT_USER = getpass.getuser()
except Exception:
    _CURRENT_USER = os.environ.get("USERNAME") or os.environ.get("USER") or ""


def redact_paths_and_users(text: str, username: str | None = None) -> str:
    """Redact Windows and Unix user directory paths and usernames from text.

    Examples:
      'C:\\Users\\aayush\\Desktop\\file.txt' -> 'C:\\Users\\<user>\\Desktop\\file.txt'
      '/home/aayush/documents' -> '/home/<user>/documents'
    """
    if not text:
        return ""

    user = username or _CURRENT_USER
    redacted = text

    # Redact Windows user paths: C:\Users\<username> or C:/Users/<username>
    redacted = re.sub(
        r"([a-zA-Z]:[/\\]Users[/\\])[^/\\\s]+",
        r"\1<user>",
        redacted,
        flags=re.IGNORECASE,
    )

    # Redact Unix user paths: /home/<username> or /Users/<username>
    redacted = re.sub(
        r"(/(?:home|Users)/)[^/\\\s]+",
        r"\1<user>",
        redacted,
    )

    # If username is known and non-trivial (at least 3 characters), redact standalone occurrences
    if user and len(user) >= 3:
        user_pattern = re.compile(rf"\b{re.escape(user)}\b", re.IGNORECASE)
        redacted = user_pattern.sub("<user>", redacted)

    return redacted


_SECRET_PATTERNS = [
    (re.compile(r"gnani_[a-zA-Z0-9_\-]{8,}", re.IGNORECASE), "[REDACTED_GNANI_TOKEN]"),
    (re.compile(r"hf_[a-zA-Z0-9_\-]{8,}", re.IGNORECASE), "[REDACTED_HF_TOKEN]"),
    (re.compile(r"sk-[a-zA-Z0-9_\-]{8,}", re.IGNORECASE), "[REDACTED_API_KEY]"),
    (re.compile(r"(Bearer\s+)[a-zA-Z0-9_\-\.]{8,}", re.IGNORECASE), r"\1[REDACTED_TOKEN]"),
]


def scrub_secrets(text: str) -> str:
    """Scrub known API key, bearer token, and credential patterns from text (§8)."""
    if not text:
        return ""
    scrubbed = text
    for pattern, replacement in _SECRET_PATTERNS:
        scrubbed = pattern.sub(replacement, scrubbed)
    return scrubbed


def sanitize_payload_for_telemetry_or_api(data: Any, username: str | None = None) -> Any:
    """Recursively scrub usernames and user paths from nested dicts/lists."""
    user = username or _CURRENT_USER
    if isinstance(data, str):
        return redact_paths_and_users(data, username=user)
    elif isinstance(data, dict):
        return {k: sanitize_payload_for_telemetry_or_api(v, username=user) for k, v in data.items()}
    elif isinstance(data, list):
        return [sanitize_payload_for_telemetry_or_api(item, username=user) for item in data]
    return data
