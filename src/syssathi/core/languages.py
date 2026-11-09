"""Language registry and detector for all Gnani-supported languages (§5.3)."""

from __future__ import annotations

import functools
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

_LANGUAGES_YAML = Path(__file__).resolve().parent / "languages.yaml"


class LanguageInfo(BaseModel):
    """Configuration metadata for a single supported language."""

    code: str
    name: str
    native_name: str
    default_script: str
    scripts: list[str] = Field(default_factory=list)
    prisma_code: str
    timbre_lang: str
    default_voice: str
    sentence_delimiters: str
    digit_zero: str
    unicode_range: list[int] = Field(default_factory=list)


class LanguageRegistry:
    """Registry managing all supported languages, script mappings, and voice defaults."""

    def __init__(self, yaml_path: Path | None = None) -> None:
        path = yaml_path or _LANGUAGES_YAML
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        self._languages: dict[str, LanguageInfo] = {
            code: LanguageInfo(**info) for code, info in data.get("languages", {}).items()
        }

    def get(self, code: str) -> LanguageInfo | None:
        """Lookup language by ISO/BCP code (e.g. 'hi', 'hi-IN', 'ta')."""
        if not code:
            return None
        clean_code = code.split("-")[0].lower()
        return self._languages.get(clean_code)

    def list_languages(self) -> list[LanguageInfo]:
        """Return all supported languages."""
        return list(self._languages.values())

    def detect_language(self, text: str, default: str = "hi") -> LanguageInfo:
        """Detect language from text based on Unicode script block presence.

        Deterministic, fast (<0.1ms), and zero-dependency.
        """
        counts: dict[str, int] = {}

        for char in text:
            cp = ord(char)
            for lang_code, lang_info in self._languages.items():
                if lang_info.unicode_range and len(lang_info.unicode_range) == 2:
                    start, end = lang_info.unicode_range
                    if start <= cp <= end:
                        counts[lang_code] = counts.get(lang_code, 0) + 1

        if counts:
            # Pick non-Latin script with highest frequency if present
            non_latin_counts = {k: v for k, v in counts.items() if k != "en"}
            if non_latin_counts:
                best_lang = max(non_latin_counts, key=non_latin_counts.get)  # type: ignore
                return self._languages[best_lang]

        # If only Latin characters or empty
        return self.get(default) or self._languages["hi"]


@functools.lru_cache(maxsize=1)
def get_language_registry() -> LanguageRegistry:
    """Return cached LanguageRegistry instance."""
    return LanguageRegistry()

