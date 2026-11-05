"""Tests for host/prompts.py — prompt content validation."""

from __future__ import annotations

from syssathi.host.prompts import (
    REPLY_PROMPT_DEVANAGARI,
    REPLY_PROMPT_LATIN,
    TOOL_ROUTING_PROMPT,
    get_reply_prompt,
)


class TestPrompts:
    """Verify prompt content and variant selection."""

    def test_reply_prompt_mentions_hinglish(self) -> None:
        assert "Hinglish" in REPLY_PROMPT_LATIN

    def test_reply_prompt_mentions_40_words(self) -> None:
        assert "40 words" in REPLY_PROMPT_LATIN

    def test_reply_prompt_no_markdown(self) -> None:
        assert "no markdown" in REPLY_PROMPT_LATIN

    def test_reply_prompt_mentions_findings(self) -> None:
        assert "findings" in REPLY_PROMPT_LATIN

    def test_devanagari_variant_mentions_devanagari(self) -> None:
        assert "Devanagari" in REPLY_PROMPT_DEVANAGARI

    def test_devanagari_has_latin_script_instruction(self) -> None:
        assert "Latin script" in REPLY_PROMPT_DEVANAGARI

    def test_tool_routing_mentions_diagnose(self) -> None:
        assert "diagnose" in TOOL_ROUTING_PROMPT.lower()

    def test_tool_routing_mentions_propose_close(self) -> None:
        assert "propose_close" in TOOL_ROUTING_PROMPT

    def test_get_reply_prompt_default(self) -> None:
        assert get_reply_prompt() == REPLY_PROMPT_LATIN

    def test_get_reply_prompt_latin(self) -> None:
        assert get_reply_prompt("latin") == REPLY_PROMPT_LATIN

    def test_get_reply_prompt_devanagari(self) -> None:
        assert get_reply_prompt("devanagari_mixed") == REPLY_PROMPT_DEVANAGARI

