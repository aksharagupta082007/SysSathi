"""Tests for <think> stripping and mock LLM backend."""

from __future__ import annotations

import json
import re

import pytest

from syssathi.host.llm import ChatResult, ToolCall, strip_think, chat, LLMUnavailable, LLMConfigurationError


class TestStripThink:
    """Strip <think>...</think> blocks from LLM output."""

    def test_no_think_block(self) -> None:
        text = "This is a normal reply."
        assert strip_think(text) == "This is a normal reply."

    def test_single_closed_block(self) -> None:
        text = "<think>some reasoning</think>The actual reply."
        assert strip_think(text) == "The actual reply."

    def test_multiple_closed_blocks(self) -> None:
        text = "<think>first</think>Hello <think>second</think>world."
        assert strip_think(text) == "Hello world."

    def test_multiline_think(self) -> None:
        text = "<think>\nline1\nline2\n</think>\nReply here."
        assert strip_think(text) == "Reply here."

    def test_unclosed_think_drops_to_end(self) -> None:
        text = "Good start. <think>this never closes and goes on"
        assert strip_think(text) == "Good start."

    def test_closed_then_unclosed(self) -> None:
        text = "<think>ok</think>Keep this. <think>unclosed part"
        assert strip_think(text) == "Keep this."

    def test_empty_think(self) -> None:
        text = "<think></think>Reply."
        assert strip_think(text) == "Reply."

    def test_only_think(self) -> None:
        text = "<think>everything is thinking</think>"
        assert strip_think(text) == ""

    def test_unclosed_at_start(self) -> None:
        text = "<think>everything drops"
        assert strip_think(text) == ""


# ---------------------------------------------------------------------------
# Helpers to extract numbers from text
# ---------------------------------------------------------------------------

def _extract_numbers(text: str) -> set[float]:
    """Extract all numbers from text."""
    nums: set[float] = set()
    for m in re.finditer(r"\d+\.?\d*", text):
        nums.add(float(m.group()))
    return nums


def _findings_numbers(findings: dict) -> set[float]:
    """Extract valid numbers from findings JSON (Addendum A2).

    A number is valid if it:
    - equals a number in findings
    - equals one rounded to a whole number
    - equals a group's ram_mb / 1000 rounded to 1 decimal
    """
    nums: set[float] = set()

    for key in ("cpu_avg_pct", "cpu_peak_pct", "ram_used_pct", "ram_total_gb",
                "disk_free_pct", "disk_mb_per_s", "startup_apps"):
        val = findings.get(key)
        if val is not None:
            nums.add(float(val))
            nums.add(float(round(val)))

    for g in findings.get("top_groups", []):
        for key in ("procs", "ram_mb", "cpu_pct"):
            val = g.get(key)
            if val is not None:
                nums.add(float(val))
                nums.add(float(round(val)))
        # ram_mb / 1000 rounded to 1 decimal
        ram_mb = g.get("ram_mb")
        if ram_mb is not None:
            nums.add(round(ram_mb / 1000, 1))

    return nums


# ---------------------------------------------------------------------------
# Mock backend tests
# ---------------------------------------------------------------------------

_SAMPLE_FINDINGS = {
    "cpu_avg_pct": 45.2,
    "cpu_peak_pct": 67.0,
    "ram_used_pct": 91.2,
    "ram_total_gb": 15.8,
    "disk_free_pct": 14.0,
    "disk_mb_per_s": 3.2,
    "top_groups": [
        {"name": "chrome", "procs": 14, "ram_mb": 3100, "cpu_pct": 22.1}
    ],
    "startup_apps": 11,
    "findings": [
        {"code": "RAM_HIGH", "message": "RAM above 85%", "severity": "high"}
    ],
}


class TestMockReply:
    """Mock backend builds a Hinglish reply from findings."""

    async def test_reply_under_40_words(self) -> None:
        messages = [
            {"role": "system", "content": "You are SysSathi."},
            {"role": "user", "content": json.dumps(_SAMPLE_FINDINGS)},
        ]
        result = await chat(messages, backend="mock")
        words = result.content.split()
        assert len(words) <= 40, f"Reply has {len(words)} words: {result.content}"

    async def test_every_number_in_reply_appears_in_findings(self) -> None:
        messages = [
            {"role": "system", "content": "You are SysSathi."},
            {"role": "user", "content": json.dumps(_SAMPLE_FINDINGS)},
        ]
        result = await chat(messages, backend="mock")
        reply_nums = _extract_numbers(result.content)
        valid_nums = _findings_numbers(_SAMPLE_FINDINGS)
        for n in reply_nums:
            assert n in valid_nums, (
                f"Number {n} in reply is not in findings. "
                f"Reply: {result.content!r}, Valid: {valid_nums}"
            )

    async def test_healthy_reply_when_no_findings(self) -> None:
        findings = dict(_SAMPLE_FINDINGS, findings=[])
        messages = [
            {"role": "system", "content": "You are SysSathi."},
            {"role": "user", "content": json.dumps(findings)},
        ]
        result = await chat(messages, backend="mock")
        assert "theek" in result.content.lower() or "healthy" in result.content.lower()

    async def test_reply_is_plain_text(self) -> None:
        messages = [
            {"role": "system", "content": "You are SysSathi."},
            {"role": "user", "content": json.dumps(_SAMPLE_FINDINGS)},
        ]
        result = await chat(messages, backend="mock")
        assert "**" not in result.content
        assert "#" not in result.content
        assert "```" not in result.content

    async def test_multiple_findings(self) -> None:
        findings = dict(_SAMPLE_FINDINGS, findings=[
            {"code": "RAM_HIGH", "message": "RAM above 85%", "severity": "high"},
            {"code": "CPU_HIGH", "message": "CPU above 80%", "severity": "high"},
        ], cpu_avg_pct=82.5)
        messages = [
            {"role": "system", "content": "You are SysSathi."},
            {"role": "user", "content": json.dumps(findings)},
        ]
        result = await chat(messages, backend="mock")
        words = result.content.split()
        assert len(words) <= 40


class TestMockToolSimulation:
    """Mock backend simulates tool calls from keyword table."""

    _DUMMY_TOOLS = [{"type": "function", "function": {"name": "get_battery_report"}}]

    async def test_battery_keyword(self) -> None:
        messages = [{"role": "user", "content": "check my battery status"}]
        result = await chat(messages, tools=self._DUMMY_TOOLS, backend="mock")
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0].name == "get_battery_report"

    async def test_startup_keyword(self) -> None:
        messages = [{"role": "user", "content": "show startup apps"}]
        result = await chat(messages, tools=self._DUMMY_TOOLS, backend="mock")
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0].name == "list_startup_apps"

    async def test_ram_keyword(self) -> None:
        messages = [{"role": "user", "content": "how much ram is being used"}]
        result = await chat(messages, tools=self._DUMMY_TOOLS, backend="mock")
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0].name == "get_top_processes"
        assert result.tool_calls[0].arguments["sort_by"] == "ram"

    async def test_band_kar_with_group(self) -> None:
        messages = [{"role": "user", "content": "chrome band kar do"}]
        result = await chat(messages, tools=self._DUMMY_TOOLS, backend="mock")
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0].name == "propose_close"
        assert result.tool_calls[0].arguments["group_name"] == "chrome"

    async def test_no_tool_without_tools_param(self) -> None:
        """Without tools, mock returns a reply even for tool keywords."""
        messages = [{"role": "user", "content": "check my battery status"}]
        result = await chat(messages, tools=None, backend="mock")
        assert len(result.tool_calls) == 0
        assert result.content  # should have a reply

    async def test_unknown_backend_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown LLM backend"):
            await chat([{"role": "user", "content": "hi"}], backend="nonexistent")

    async def test_evon_failure_raises_llm_unavailable_not_mock(self, monkeypatch) -> None:
        """Evon failure must raise LLMUnavailable and NEVER silently fall back to mock."""
        from unittest.mock import AsyncMock
        mock_client = AsyncMock()
        mock_client.chat.completions.create.side_effect = RuntimeError("503 Server Unavailable")
        monkeypatch.setattr("syssathi.host.llm._get_evon_client", lambda: mock_client)
        monkeypatch.setattr("syssathi.host.llm._evon_cached_model", "test-model")
        monkeypatch.setattr("syssathi.host.config.OPENAI_COMPAT_BASE_URL", "")

        with pytest.raises(LLMUnavailable):
            await chat([{"role": "user", "content": "slow"}], backend="evon_remote")

    async def test_unset_backend_raises_configuration_error(self, monkeypatch) -> None:
        monkeypatch.setattr("syssathi.host.config.get_llm_backend", lambda: "unset")
        with pytest.raises(LLMConfigurationError):
            await chat([{"role": "user", "content": "hello"}], backend=None)

