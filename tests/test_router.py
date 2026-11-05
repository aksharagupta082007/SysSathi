"""Tests for host/router.py — keyword matching with Addendum A4 whole-word rules."""

from __future__ import annotations

import pytest

from syssathi.host.router import route


KEYWORDS = [
    "slow",
    "hang",
    "lag",
    "laggy",
    "dheema",
    "dhima",
    "atak",
    "freeze",
    "slow chal",
]


class TestRouterKeywords:
    """Each keyword triggers the fast path."""

    @pytest.mark.parametrize("kw", KEYWORDS)
    def test_each_keyword_routes_fast(self, kw: str) -> None:
        assert route(kw, keywords=KEYWORDS) == "fast"

    @pytest.mark.parametrize("kw", KEYWORDS)
    def test_keyword_in_sentence(self, kw: str) -> None:
        assert route(f"mera laptop {kw} hai", keywords=KEYWORDS) == "fast"


class TestRouterCaseAndPunctuation:
    """Case-insensitive, punctuation stripped."""

    def test_uppercase(self) -> None:
        assert route("SLOW", keywords=KEYWORDS) == "fast"

    def test_mixed_case(self) -> None:
        assert route("Laptop Hang ho gaya", keywords=KEYWORDS) == "fast"

    def test_with_punctuation(self) -> None:
        assert route("laptop slow!!", keywords=KEYWORDS) == "fast"

    def test_with_comma(self) -> None:
        assert route("lag, bohot lag", keywords=KEYWORDS) == "fast"

    def test_question_mark(self) -> None:
        assert route("kya slow hai?", keywords=KEYWORDS) == "fast"


class TestRouterPhraseMatching:
    """Multi-word phrase 'slow chal' matches as a whole phrase."""

    def test_slow_chal_matches(self) -> None:
        assert route("mera laptop slow chal raha hai", keywords=KEYWORDS) == "fast"

    def test_slow_chal_with_punctuation(self) -> None:
        assert route("Slow chal! raha hai", keywords=KEYWORDS) == "fast"


class TestRouterWholeWord:
    """Addendum A4: never match a keyword inside a longer word."""

    def test_language_does_not_match_lag(self) -> None:
        assert route("change the language", keywords=KEYWORDS) == "evon"

    def test_flag_does_not_match_lag(self) -> None:
        assert route("flag this issue", keywords=KEYWORDS) == "evon"

    def test_slag_does_not_match_lag(self) -> None:
        assert route("remove the slag", keywords=KEYWORDS) == "evon"

    def test_slowing_does_not_match_slow(self) -> None:
        # "slowing" does NOT match "slow" as a whole word — \b requires
        # a word/non-word boundary and 'i' in 'slowing' is a word char.
        # A4 says whole words only, so this is correct behaviour.
        assert route("it is slowing down", keywords=KEYWORDS) == "evon"

    def test_freezer_does_not_match_freeze(self) -> None:
        # "freezer" — \b between 'freeze' and 'r' still fires
        # But the user said "whole words" in A4
        # Let's check: \bfreeze\b does NOT match "freezer" because
        # 'r' is a word char so there's no boundary after 'freeze' in 'freezer'
        assert route("open the freezer", keywords=KEYWORDS) == "evon"


class TestRouterEvonRoute:
    """Non-matching text goes to evon."""

    def test_unrelated(self) -> None:
        assert route("what is the weather today", keywords=KEYWORDS) == "evon"

    def test_empty(self) -> None:
        assert route("", keywords=KEYWORDS) == "evon"

    def test_hello(self) -> None:
        assert route("hello", keywords=KEYWORDS) == "evon"
