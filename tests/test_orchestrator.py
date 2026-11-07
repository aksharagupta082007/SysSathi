"""Unit tests for Orchestrator, MCP client schemas, reply guard, and test helpers."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest import mock

import pytest

from syssathi.host.llm import ChatResult, ToolCall
from syssathi.host.orchestrator import Orchestrator, apply_reply_guard
from tests.test_helpers import (
    collect_allowed_numbers,
    extract_numbers_from_text,
    verify_reply_numbers,
)


class FakeMCPClient:
    """Fake MCP client for fast, deterministic unit testing."""

    def __init__(self) -> None:
        self.approval_token = "fake-secret-token"
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.tool_schemas: dict[str, Any] = {
            "diagnose_slowness": {"type": "object", "properties": {}},
            "get_top_processes": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer"},
                    "sort_by": {"type": "string", "enum": ["ram", "cpu"]},
                },
            },
            "list_startup_apps": {"type": "object", "properties": {}},
            "get_battery_report": {"type": "object", "properties": {}},
            "propose_close": {
                "type": "object",
                "properties": {"group_name": {"type": "string"}},
                "required": ["group_name"],
            },
            "execute_action": {
                "type": "object",
                "properties": {
                    "action_id": {"type": "string"},
                    "approval_token": {"type": "string"},
                },
                "required": ["action_id", "approval_token"],
            },
        }

    def get_evon_tool_schemas(self) -> list[dict[str, Any]]:
        # Exclude execute_action
        return [
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": f"Description for {name}",
                    "parameters": schema,
                },
            }
            for name, schema in self.tool_schemas.items()
            if name != "execute_action"
        ]

    def get_tool_schema(self, tool_name: str) -> dict[str, Any] | None:
        return self.tool_schemas.get(tool_name)

    async def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> Any:
        args = arguments or {}
        self.calls.append((name, args))

        if name == "diagnose_slowness":
            return {
                "cpu_avg_pct": 82.5,
                "cpu_peak_pct": 94.0,
                "ram_used_pct": 91.2,
                "ram_total_gb": 16.0,
                "disk_free_pct": 15.0,
                "disk_mb_per_s": 4.1,
                "startup_apps": 5,
                "top_groups": [
                    {"name": "chrome", "procs": 12, "ram_mb": 3100, "cpu_pct": 25.0},
                    {"name": "explorer", "procs": 1, "ram_mb": 200, "cpu_pct": 1.0},
                ],
                "findings": [
                    {"code": "RAM_HIGH", "message": "RAM above 85%", "severity": "high"}
                ],
            }
        elif name == "propose_close":
            group = args.get("group_name", "")
            return {
                "action_id": "test-uuid-1234",
                "description": f"Close {group}",
                "expires_in_s": 60,
            }
        elif name == "execute_action":
            return {
                "action_id": args.get("action_id"),
                "closed_count": 12,
                "skipped_count": 0,
                "failed_count": 0,
            }
        elif name == "get_battery_report":
            return {"has_battery": True, "charge_pct": 85, "plugged": True}
        return {}


# ---------------------------------------------------------------------------
# Test Number Check (Addendum A2)
# ---------------------------------------------------------------------------

class TestNumberCheckHelper:
    def test_extract_numbers(self):
        text = "RAM 91% use ho rahi hai. Chrome ke 14 processes 3.1 GB le rahe hain."
        nums = extract_numbers_from_text(text)
        assert nums == [91.0, 14.0, 3.1]

    def test_allowed_numbers_collection(self):
        findings = {
            "ram_used_pct": 91.2,
            "ram_total_gb": 16.0,
            "top_groups": [{"name": "chrome", "procs": 14, "ram_mb": 3100}],
        }
        allowed = collect_allowed_numbers(findings)
        assert 91.2 in allowed
        assert 91.0 in allowed  # rounded whole
        assert 16.0 in allowed
        assert 14.0 in allowed
        assert 3.1 in allowed   # 3100 / 1000 = 3.1
        assert 3.0 in allowed   # rounded 3.1

    def test_verify_reply_numbers_valid(self):
        findings = {
            "ram_used_pct": 91.2,
            "top_groups": [{"name": "chrome", "procs": 14, "ram_mb": 3100}],
        }
        reply = "RAM 91% use ho rahi hai. Chrome ke 14 processes 3.1 GB le rahe hain."
        valid, invalid = verify_reply_numbers(reply, findings)
        assert valid
        assert invalid == []

    def test_verify_reply_numbers_invalid(self):
        findings = {"ram_used_pct": 91.2}
        reply = "RAM 91% use ho rahi hai. 99 apps band kar do."
        valid, invalid = verify_reply_numbers(reply, findings)
        assert not valid
        assert 99.0 in invalid


# ---------------------------------------------------------------------------
# Test Reply Guard (Addendum A3)
# ---------------------------------------------------------------------------

class TestReplyGuard:
    def test_strips_markdown_and_emoji(self):
        text = "Hello **world**! 😊 [Click here](url) `test`"
        guarded = apply_reply_guard(text)
        assert "world" in guarded
        assert "**" not in guarded
        assert "😊" not in guarded
        assert "[" not in guarded

    def test_truncates_at_sentence_within_40_words(self):
        # 3 sentences, total 50 words
        sentence1 = "Ye pehla sentence hai jo laptop ke baare me batata hai."  # 10 words
        sentence2 = "Doosra sentence Chrome ke RAM lene ke baare me hai."  # 9 words
        sentence3 = " ".join(["extra"] * 35) + "."
        full_text = f"{sentence1} {sentence2} {sentence3}"

        guarded = apply_reply_guard(full_text, max_words=40)
        words = guarded.split()
        assert len(words) <= 40
        assert guarded.endswith(".")
        assert "Doosra sentence" in guarded


# ---------------------------------------------------------------------------
# Test Orchestrator
# ---------------------------------------------------------------------------

class TestOrchestrator:
    @pytest.fixture(autouse=True)
    def _force_mock_backend(self, monkeypatch):
        monkeypatch.setattr("syssathi.host.config.LLM_BACKEND", "mock")

    @pytest.mark.asyncio
    async def test_fast_route_with_addendum_a1_proposal(self):
        fake_mcp = FakeMCPClient()
        orch = Orchestrator(fake_mcp)

        # "slow chal raha hai" triggers fast route
        with mock.patch("syssathi.host.orchestrator.FORCE_FAST_PATH", True):
            reply, timer = await orch.handle_message("Mera laptop slow chal raha hai")

        assert timer.route == "fast"
        assert len(reply.split()) <= 40
        # diagnose_slowness must have been called
        assert any(c[0] == "diagnose_slowness" for c in fake_mcp.calls)
        # Addendum A1: propose_close on first non-protected group ("chrome")
        assert any(c[0] == "propose_close" and c[1].get("group_name") == "chrome" for c in fake_mcp.calls)
        # Pending proposal should be stored
        assert orch.pending_proposal is not None
        assert orch.pending_proposal["action_id"] == "test-uuid-1234"

    @pytest.mark.asyncio
    async def test_approve_flow(self):
        fake_mcp = FakeMCPClient()
        orch = Orchestrator(fake_mcp)

        # Set a pending proposal
        orch.pending_proposal = {"action_id": "prop-456"}
        res = await orch.approve()

        assert res["closed_count"] == 12
        assert orch.pending_proposal is None
        # Verify execute_action received approval_token
        exec_call = [c for c in fake_mcp.calls if c[0] == "execute_action"][0]
        assert exec_call[1]["action_id"] == "prop-456"
        assert exec_call[1]["approval_token"] == fake_mcp.approval_token

    @pytest.mark.asyncio
    async def test_evon_route_rejects_execute_action_from_model(self):
        fake_mcp = FakeMCPClient()
        orch = Orchestrator(fake_mcp)

        # Force evon route and simulate model returning an unauthorized tool call: execute_action
        disallowed_call = ToolCall(name="execute_action", arguments={"action_id": "bad"})
        fake_result = ChatResult(content="", tool_calls=[disallowed_call])

        with mock.patch("syssathi.host.orchestrator.FORCE_FAST_PATH", False):
            with mock.patch("syssathi.host.orchestrator.chat", return_value=fake_result):
                reply, timer = await orch.handle_message("close it")

        assert "Mujhe samajh nahi aaya" in reply
        # MCP server should NOT have executed execute_action
        assert not any(c[0] == "execute_action" for c in fake_mcp.calls)

    @pytest.mark.asyncio
    async def test_evon_route_rejects_invalid_tool_args(self):
        fake_mcp = FakeMCPClient()
        orch = Orchestrator(fake_mcp)

        # propose_close requires 'group_name' string, provide invalid type
        bad_arg_call = ToolCall(name="propose_close", arguments={"group_name": 12345})
        fake_result = ChatResult(content="", tool_calls=[bad_arg_call])

        with mock.patch("syssathi.host.orchestrator.FORCE_FAST_PATH", False):
            with mock.patch("syssathi.host.orchestrator.chat", return_value=fake_result):
                reply, timer = await orch.handle_message("band kar do")

        assert "Mujhe samajh nahi aaya" in reply
        assert not any(c[0] == "propose_close" for c in fake_mcp.calls)

    @pytest.mark.asyncio
    async def test_history_window_stays_at_most_6_messages(self):
        fake_mcp = FakeMCPClient()
        orch = Orchestrator(fake_mcp)

        # Send 5 messages (each turn adds 1 user + 1 assistant = 2 messages)
        for i in range(5):
            await orch.handle_message(f"Hello test message {i}")

        assert len(orch.messages) <= 6
