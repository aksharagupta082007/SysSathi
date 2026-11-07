"""Orchestrator managing conversation, tool calls, and proposal lifecycle."""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Protocol

import jsonschema

from syssathi.host.config import FORCE_FAST_PATH, REPLY_STYLE
from syssathi.host.llm import ChatResult, ToolCall, chat
from syssathi.host.mcp_client import ALLOWED_EVON_TOOLS, MCPClient
from syssathi.host.prompts import (
    TOOL_ROUTING_PROMPT,
    get_reply_prompt,
)
from syssathi.host.router import route
from syssathi.host.timing import Timer
from syssathi.mcp_server.policy import is_protected

logger = logging.getLogger(__name__)

# Addendum A3 reply guard regexes
_MARKDOWN_RE = re.compile(r"[*_~`#\[\]\(\)>+]")
_EMOJI_RE = re.compile(
    "["
    "\U0001F600-\U0001F64F"  # emoticons
    "\U0001F300-\U0001F5FF"  # symbols & pictographs
    "\U0001F680-\U0001F6FF"  # transport & map
    "\U0001F1E0-\U0001F1FF"  # flags
    "\U00002702-\U000027B0"
    "\U000024C2-\U0001F251"
    "]+",
    flags=re.UNICODE,
)


def apply_reply_guard(text: str, max_words: int = 40) -> str:
    """Apply Addendum A3: strip markdown, emoji, and limit to 40 words ending at sentence end."""
    # Strip markdown and emoji
    clean = _MARKDOWN_RE.sub("", text)
    clean = _EMOJI_RE.sub("", clean)
    # Collapse extra whitespace
    clean = " ".join(clean.split())

    words = clean.split()
    if len(words) <= max_words:
        return clean

    # Cut to max_words words
    cut_words = words[:max_words]
    cut_text = " ".join(cut_words)

    # Try to end at the last sentence boundary inside the limit (. ? ! or Hindi danda ।)
    sentence_matches = list(re.finditer(r"[.?!।]", cut_text))
    if sentence_matches:
        last_punct = sentence_matches[-1]
        return cut_text[: last_punct.end()].strip()

    return cut_text.strip()


class MCPClientProtocol(Protocol):
    """Protocol for MCP client to allow testing with fakes."""
    approval_token: str
    def get_evon_tool_schemas(self) -> list[dict[str, Any]]: ...
    def get_tool_schema(self, tool_name: str) -> dict[str, Any] | None: ...
    async def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> Any: ...


class Orchestrator:
    """Session orchestrator coordinating LLM, MCP tools, and proposals."""

    def __init__(self, mcp_client: MCPClientProtocol) -> None:
        self.mcp = mcp_client
        self.messages: list[dict[str, str]] = []
        self.pending_proposal: dict[str, Any] | None = None
        self.latest_findings: dict[str, Any] | None = None

    def _add_message(self, role: str, content: str) -> None:
        """Add message to history and enforce 6-message window."""
        self.messages.append({"role": role, "content": content})
        if len(self.messages) > 6:
            self.messages = self.messages[-6:]

    async def handle_message(self, user_text: str) -> tuple[str, Timer]:
        """Process user message, return guarded Hinglish reply and timer."""
        timer = Timer()
        r = route(user_text) if FORCE_FAST_PATH else "evon"
        timer.set("route", r)

        if r == "fast":
            reply = await self._handle_fast_path(user_text, timer)
        else:
            reply = await self._handle_evon_path(user_text, timer)

        guarded_reply = apply_reply_guard(reply, max_words=40)
        timer.flush()
        return guarded_reply, timer

    async def _handle_fast_path(self, user_text: str, timer: Timer) -> str:
        """Execute fast path: diagnose_slowness -> A1 propose_close -> Evon narration."""
        # 1. Tool call: diagnose_slowness
        t0 = timer.elapsed_ms()
        findings = await self.mcp.call_tool("diagnose_slowness", {})
        timer.mark("tool_ms", timer._start + t0 / 1000.0)
        self.latest_findings = findings if isinstance(findings, dict) else {}

        # 2. Addendum A1: Propose close if RAM_HIGH or CPU_HIGH
        proposal_info: dict[str, Any] | None = None
        if isinstance(findings, dict):
            finding_codes = {f.get("code") for f in findings.get("findings", [])}
            if "RAM_HIGH" in finding_codes or "CPU_HIGH" in finding_codes:
                top_groups = findings.get("top_groups", [])
                for group in top_groups:
                    group_name = group.get("name", "")
                    if group_name and not is_protected(group_name):
                        prop = await self.mcp.call_tool(
                            "propose_close", {"group_name": group_name}
                        )
                        if isinstance(prop, dict) and not prop.get("refused"):
                            self.pending_proposal = prop
                            proposal_info = prop
                        break

        # 3. Evon reply call
        system_prompt = get_reply_prompt(REPLY_STYLE)
        user_prompt_data = {"findings": findings}
        if proposal_info:
            user_prompt_data["proposal"] = proposal_info

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(user_prompt_data)},
        ]

        t1 = timer.elapsed_ms()
        result = chat(messages=messages, tools=None)
        timer.mark("llm1_ms", timer._start + t1 / 1000.0)

        self._add_message(role="user", content=user_text)
        self._add_message(role="assistant", content=result.content)
        return result.content

    async def _handle_evon_path(self, user_text: str, timer: Timer) -> str:
        """Execute evon route: tool-routing call -> validate -> tool call -> reply call."""
        self._add_message(role="user", content=user_text)

        # Build context for Call 1 (last 6 messages with system prompt)
        call1_messages = [
            {"role": "system", "content": TOOL_ROUTING_PROMPT},
            *self.messages,
        ]

        tool_schemas = self.mcp.get_evon_tool_schemas()

        t0 = timer.elapsed_ms()
        call1_result = chat(messages=call1_messages, tools=tool_schemas)
        timer.mark("llm1_ms", timer._start + t0 / 1000.0)

        # If Evon didn't call any tool, return its content directly
        if not call1_result.tool_calls:
            self._add_message(role="assistant", content=call1_result.content)
            return call1_result.content

        # One tool call allowed per turn
        tool_call = call1_result.tool_calls[0]
        tool_name = tool_call.name
        tool_args = tool_call.arguments

        # 1. Allowlist validation (strict check, reject execute_action or unknowns)
        if tool_name not in ALLOWED_EVON_TOOLS:
            logger.warning("Rejected disallowed tool call: %s", tool_name)
            safe_reply = "Mujhe samajh nahi aaya, kya aap dobara bol sakte hain?"
            self._add_message(role="assistant", content=safe_reply)
            return safe_reply

        # 2. Argument validation with jsonschema
        tool_schema = self.mcp.get_tool_schema(tool_name)
        if tool_schema:
            try:
                jsonschema.validate(tool_args, tool_schema)
            except jsonschema.ValidationError as err:
                logger.warning("Tool arguments schema validation failed for %s: %s", tool_name, err)
                safe_reply = "Mujhe samajh nahi aaya, kya aap dobara bol sakte hain?"
                self._add_message(role="assistant", content=safe_reply)
                return safe_reply

        # 3. Call tool via MCP
        t1 = timer.elapsed_ms()
        tool_output = await self.mcp.call_tool(tool_name, tool_args)
        timer.mark("tool_ms", timer._start + t1 / 1000.0)

        if tool_name == "diagnose_slowness" and isinstance(tool_output, dict):
            self.latest_findings = tool_output
        elif tool_name == "propose_close" and isinstance(tool_output, dict):
            if not tool_output.get("refused"):
                self.pending_proposal = tool_output

        # Truncate tool output to 2,000 chars
        tool_output_str = json.dumps(tool_output) if not isinstance(tool_output, str) else tool_output
        if len(tool_output_str) > 2000:
            tool_output_str = tool_output_str[:2000]

        # 4. LLM Call 2: Generate reply from tool result
        reply_sys_prompt = get_reply_prompt(REPLY_STYLE)
        call2_messages = [
            {"role": "system", "content": reply_sys_prompt},
            *self.messages,
            {"role": "user", "content": f"Tool result from {tool_name}:\n{tool_output_str}"},
        ]

        t2 = timer.elapsed_ms()
        call2_result = chat(messages=call2_messages, tools=None)
        timer.mark("llm2_ms", timer._start + t2 / 1000.0)

        self._add_message(role="assistant", content=call2_result.content)
        return call2_result.content

    async def approve(self) -> dict[str, Any]:
        """Execute pending proposal via execute_action."""
        if not self.pending_proposal:
            return {"error": "No pending proposal to approve"}

        action_id = self.pending_proposal.get("action_id")
        if not action_id:
            return {"error": "Pending proposal is missing action_id"}

        # Execute action using the secret approval token
        result = await self.mcp.call_tool(
            "execute_action",
            {
                "action_id": action_id,
                "approval_token": self.mcp.approval_token,
            },
        )
        self.pending_proposal = None
        return result
