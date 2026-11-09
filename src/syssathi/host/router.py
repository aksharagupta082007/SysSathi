"""Multilingual Intent Router — fast-path routing and intent classification (§5.2)."""

from __future__ import annotations

import re
import unicodedata
from typing import Any

import regex

from syssathi.host.config import SLOWNESS_KEYWORDS

# Multilingual slowness vocabulary across supported Indic scripts and Latin
MULTILINGUAL_SLOWNESS_KEYWORDS: list[str] = list(SLOWNESS_KEYWORDS) + [
    # Hindi / Marathi (Devanagari)
    "धीमा", "धीमे", "धीमी", "अटक", "अटकता", "अटकती", "लैक", "हैंग", "सुस्त", "हळू", "हँग", "अडकतो",
    # Bengali
    "ধীর", "আটকে", "হ্যাং",
    # Tamil
    "மெதுவாக", "மெதுவா", "ஹேங்",
    # Telugu
    "నెమ్మదిగా", "హాంగ్", "స్లో",
    # Gujarati
    "ધીમું", "ધીમી", "હેંગ",
    # Kannada
    "ನಿಧಾನ", "ಹ್ಯಾಂಗ್",
    # Malayalam
    "പതുക്കെ", "ഹാംഗ്",
    # Punjabi
    "ਹੌਲੀ", "ਹੈਂਗ",
    # Odia
    "ଧୀର", "ହ୍ୟାଙ୍ଗ",
    # Urdu
    "سست", "ہینگ",
]


def _normalize(text: str) -> str:
    """Lowercase, strip punctuation and symbols while preserving all Unicode letters and combining marks."""
    text = text.lower()
    # Strip punctuation and symbols, preserving letters, combining marks (vowel signs), and numbers
    text = regex.sub(r"[\p{P}\p{S}]+", " ", text)
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _build_pattern(keywords: list[str]) -> re.Pattern[str]:
    """Build a regex matching any keyword as a whole word or phrase."""
    sorted_kw = sorted(keywords, key=len, reverse=True)
    escaped = [re.escape(kw.lower()) for kw in sorted_kw]
    pattern = r"\b(?:" + "|".join(escaped) + r")\b"
    return re.compile(pattern, re.UNICODE)


_DEFAULT_PATTERN: re.Pattern[str] = _build_pattern(MULTILINGUAL_SLOWNESS_KEYWORDS)


def classify_intent(text: str) -> str:
    """Classify user intent into one of the core skills or sub-tasks."""
    lower = text.lower()
    norm = _normalize(text)

    # Slowness / Diagnose
    if _DEFAULT_PATTERN.search(norm):
        return "diagnose"

    # Battery
    battery_terms = ["battery", "charge", "charging", "बैटरी", "चार्ज", "ব্যাটারি", "பேட்டரி", "బ్యాటరీ"]
    if any(b in lower for b in battery_terms):
        return "battery"

    # Startup
    startup_terms = ["startup", "boot", "start up", "स्टार्टअप", "बूट", "স্টার্টআপ"]
    if any(s in lower for s in startup_terms):
        return "startup"

    # Processes
    proc_terms = ["process", "task manager", "ram use", "memory use", "processes"]
    if any(p in lower for p in proc_terms):
        return "processes"

    # Errors
    if "error" in lower or re.search(r"0x[0-9a-fA-F]{4,8}", text):
        return "errors"

    # How-to
    howto_terms = ["kaise karein", "kaise karu", "kaise badlu", "how to", "how do i", "কিভাবে", "எப்படி", "ఎలా"]
    if any(h in lower for h in howto_terms):
        return "howto"

    # Tool finder
    tool_terms = ["software", "download", "free mein", "tool", "app", "editor"]
    if any(t in lower for t in tool_terms):
        return "toolfinder"

    # Explain
    explain_terms = ["kya hota hai", "kya hai", "what is", "explain", "samjhao", "meaning", "vpn", "malware", "dns"]
    if any(e in lower for e in explain_terms):
        return "explain"

    return "general"


def route(text: str, keywords: list[str] | None = None) -> str:
    """Return 'fast' if text matches a slowness query, else 'evon'."""
    normalized = _normalize(text)

    if keywords is not None:
        pattern = _build_pattern(keywords)
    else:
        pattern = _DEFAULT_PATTERN

    if pattern.search(normalized):
        return "fast"

    # Check multilingual substring for non-Latin scripts where \b may vary
    if keywords is None:
        for kw in MULTILINGUAL_SLOWNESS_KEYWORDS:
            if any(ord(c) > 127 for c in kw) and kw in normalized:
                return "fast"

    return "evon"
