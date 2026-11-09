"""Orchestrator managing conversation, tool calls, event streaming, and proposal lifecycle."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import secrets
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Protocol

import regex

from syssathi.grounding import (
    format_template_reply,
    verify_reply_citations,
    verify_reply_numbers,
)
from syssathi.host.config import ENABLE_FAST_PATH, FORCE_FAST_PATH, REPLY_STYLE
from syssathi.host.llm import ChatResult, ToolCall, chat
from syssathi.host.mcp_client import ALLOWED_EVON_TOOLS, MCPClient
from syssathi.host.prompts import (
    TOOL_ROUTING_PROMPT,
    get_reply_prompt,
)
from syssathi.host.router import route
from syssathi.host.timing import Timer
from syssathi.host.validation import validate_tool_call
from syssathi.mcp_server.policy import is_protected
from syssathi.voice.splitter import SentenceSplitter

logger = logging.getLogger(__name__)

# Addendum A3 reply guard regexes
_EMOJI_RE = regex.compile(r"[\p{Extended_Pictographic}\p{Emoji_Presentation}\uFE0E\uFE0F]+")


def _strip_markdown(text: str) -> str:
    """Strip markdown formatting while preserving normal punctuation and brackets."""
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"\*([^*]+)\*", r"\1", text)
    text = re.sub(r"__([^_]+)__", r"\1", text)
    text = re.sub(r"_([^_]+)_", r"\1", text)
    text = re.sub(r"~~([^~]+)~~", r"\1", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"(?m)^[#>]+\s*", "", text)
    text = re.sub(r"(?m)^[\*\-\+]\s+", "", text)
    text = re.sub(r"[*_~`#]", "", text)
    return text


def apply_reply_guard(text: str, max_words: int = 40) -> str:
    """Apply Addendum A3: strip markdown, emoji, and limit to 40 words ending at sentence end."""
    clean = _strip_markdown(text)
    clean = _EMOJI_RE.sub("", clean)
    clean = " ".join(clean.split())

    words = clean.split()
    if len(words) <= max_words:
        return clean

    cut_words = words[:max_words]
    cut_text = " ".join(cut_words)

    # End at the last sentence boundary inside the limit
    sentence_matches = list(re.finditer(r"[.?!।॥。？！؟۔]", cut_text))
    if sentence_matches:
        last_punct = sentence_matches[-1]
        return cut_text[: last_punct.end()].strip()

    return cut_text.strip()


@dataclass
class Event:
    """Event emitted during an orchestrator turn (4.2)."""

    type: str  # "route" | "filler" | "sentence" | "tool_call" | "tool_result" | "proposal" | "reply" | "error" | "done"
    data: dict[str, Any] = field(default_factory=dict)
    text: str = ""


@dataclass
class Session:
    """Session container holding state, history, and active proposal for one user (4.2)."""

    session_id: str
    language: str = "hi"
    script: str = "latin"
    history: list[dict[str, str]] = field(default_factory=list)
    last_tool_result: dict[str, Any] | None = None
    pending_proposal: dict[str, Any] | None = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def add_message(self, role: str, content: str) -> None:
        """Add message to history with 6-message window cap."""
        self.history.append({"role": role, "content": content})
        if len(self.history) > 6:
            self.history = self.history[-6:]


class MCPClientProtocol(Protocol):
    """Protocol for MCP client to allow testing with fakes."""

    approval_token: str
    def get_evon_tool_schemas(self) -> list[dict[str, Any]]: ...
    def get_tool_schema(self, tool_name: str) -> dict[str, Any] | None: ...
    async def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> Any: ...


class Orchestrator:
    """Session orchestrator coordinating LLM, MCP tools, and event streaming."""

    def __init__(self, mcp_client: MCPClientProtocol) -> None:
        self.mcp = mcp_client
        self.default_session = Session(session_id="default")
        self.latest_findings: dict[str, Any] | None = None

    @property
    def messages(self) -> list[dict[str, str]]:
        return self.default_session.history

    @messages.setter
    def messages(self, value: list[dict[str, str]]) -> None:
        self.default_session.history = value

    @property
    def pending_proposal(self) -> dict[str, Any] | None:
        return self.default_session.pending_proposal

    @pending_proposal.setter
    def pending_proposal(self, value: dict[str, Any] | None) -> None:
        self.default_session.pending_proposal = value

    def _add_message(self, role: str, content: str) -> None:
        self.default_session.add_message(role, content)

    async def run_turn(self, session: Session, user_input: str) -> AsyncIterator[Event]:
        """Execute a full turn as an event stream (4.2)."""
        async with session.lock:
            timer = Timer()
            fast_enabled = FORCE_FAST_PATH if FORCE_FAST_PATH is not None else ENABLE_FAST_PATH
            r = route(user_input) if fast_enabled else "evon"
            timer.set("route", r)
            yield Event(type="route", data={"route": r})

            if r == "fast":
                async for evt in self._run_fast_turn(session, user_input, timer):
                    yield evt
            else:
                async for evt in self._run_evon_turn(session, user_input, timer):
                    yield evt

    async def _run_fast_turn(
        self, session: Session, user_input: str, timer: Timer
    ) -> AsyncIterator[Event]:
        """Execute fast path turn."""
        yield Event(type="filler", text="Ek second, check karta hoon")

        # 1. Tool call: diagnose_slowness
        yield Event(type="tool_call", data={"name": "diagnose_slowness", "args": {}})
        t0 = timer.elapsed_ms()
        findings = await self.mcp.call_tool("diagnose_slowness", {})
        timer.mark("tool_ms", timer._start + t0 / 1000.0)
        self.latest_findings = findings if isinstance(findings, dict) else {}
        session.last_tool_result = self.latest_findings
        yield Event(type="tool_result", data={"name": "diagnose_slowness", "result": findings})

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
                            session.pending_proposal = prop
                            self.pending_proposal = prop
                            proposal_info = prop
                            yield Event(type="proposal", data=prop)
                        break

        # 3. Evon reply call
        system_prompt = get_reply_prompt(session.script or REPLY_STYLE, language=session.language)
        user_prompt_data = {"findings": findings}
        if proposal_info:
            user_prompt_data["proposal"] = proposal_info

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(user_prompt_data)},
        ]

        t1 = timer.elapsed_ms()
        try:
            result = await chat(messages=messages, tools=None)
        except Exception as e:
            logger.exception("LLM call failed in fast path: %s", e)
            err_msg = "Kshama karein, AI service abhi uplabdh nahi hai. Kripya thodi der baad dobara koshish karein."
            yield Event(type="error", text=err_msg)
            yield Event(type="reply", text=err_msg)
            timer.flush()
            yield Event(type="done", data={"total_ms": timer.total_ms})
            return

        timer.mark("llm1_ms", timer._start + t1 / 1000.0)
        reply_text = result.content

        # Runtime Grounding Check (§4.5)
        if isinstance(findings, dict):
            is_valid, invalid_nums = verify_reply_numbers(reply_text, findings)
            if not is_valid:
                logger.warning(
                    "Grounding check failed on numbers %s in fast path. Regenerating...",
                    invalid_nums,
                )
                retry_messages = [
                    *messages,
                    {"role": "assistant", "content": reply_text},
                    {
                        "role": "user",
                        "content": "IMPORTANT: You used numbers not in findings. State the findings using ONLY the exact numbers provided in findings JSON.",
                    },
                ]
                try:
                    retry_res = await chat(messages=retry_messages, tools=None)
                    is_valid2, _ = verify_reply_numbers(retry_res.content, findings)
                    if is_valid2:
                        reply_text = retry_res.content
                    else:
                        logger.warning(
                            "Regeneration still ungrounded. Falling back to deterministic template."
                        )
                        reply_text = format_template_reply(findings)
                except Exception:
                    reply_text = format_template_reply(findings)

        guarded = apply_reply_guard(reply_text, max_words=40)
        session.add_message("user", user_input)
        session.add_message("assistant", guarded)

        # Educational lesson card (Teach, don't just do - Principle 1)
        from syssathi.skills import resolve_skill
        skill = resolve_skill(user_input, "diagnose")
        if hasattr(skill, "build_lesson_card") and findings:
            card = skill.build_lesson_card(findings)
            if card:
                yield Event(
                    type="lesson_card",
                    data={
                        "title": card.title,
                        "summary": card.summary,
                        "actionable_tip": card.actionable_tip,
                        "external_link": card.external_link,
                    },
                )

        # Sentence streaming for fast TTS time-to-first-byte
        splitter = SentenceSplitter()
        for s in splitter.push(guarded) + splitter.flush():
            yield Event(type="sentence", text=s)

        yield Event(type="reply", text=guarded)
        timer.flush()
        yield Event(type="done", data={"total_ms": timer.total_ms})

    async def _run_evon_turn(
        self, session: Session, user_input: str, timer: Timer
    ) -> AsyncIterator[Event]:
        """Execute evon path turn."""
        session.add_message("user", user_input)

        call1_messages = [
            {"role": "system", "content": TOOL_ROUTING_PROMPT},
            *session.history,
        ]

        tool_schemas = self.mcp.get_evon_tool_schemas()
        t0 = timer.elapsed_ms()
        try:
            call1_result = await chat(messages=call1_messages, tools=tool_schemas)
        except Exception as e:
            logger.exception("LLM call 1 failed in evon path: %s", e)
            err_msg = "Kshama karein, AI service abhi uplabdh nahi hai. Kripya thodi der baad dobara koshish karein."
            yield Event(type="error", text=err_msg)
            yield Event(type="reply", text=err_msg)
            timer.flush()
            yield Event(type="done", data={"total_ms": timer.total_ms})
            return

        timer.mark("llm1_ms", timer._start + t0 / 1000.0)

        # If Evon didn't call any tool, return its content directly
        if not call1_result.tool_calls:
            guarded = apply_reply_guard(call1_result.content, max_words=40)
            session.add_message("assistant", guarded)
            splitter = SentenceSplitter()
            for s in splitter.push(guarded) + splitter.flush():
                yield Event(type="sentence", text=s)
            yield Event(type="reply", text=guarded)
            timer.flush()
            yield Event(type="done", data={"total_ms": timer.total_ms})
            return

        tool_call = call1_result.tool_calls[0]
        tool_name = tool_call.name
        tool_args = tool_call.arguments

        # 1. Validation
        tool_schema_map = {tool_name: self.mcp.get_tool_schema(tool_name)}
        is_valid, err = validate_tool_call(tool_name, tool_args, tool_schema_map)
        if not is_valid:
            logger.warning("Tool call validation rejected for %s: %s", tool_name, err)
            safe_reply = "Mujhe samajh nahi aaya, kya aap dobara bol sakte hain?"
            session.add_message("assistant", safe_reply)
            yield Event(type="reply", text=safe_reply)
            timer.flush()
            yield Event(type="done", data={"total_ms": timer.total_ms})
            return

        # 2. Tool call
        yield Event(type="tool_call", data={"name": tool_name, "args": tool_args})
        t1 = timer.elapsed_ms()
        try:
            tool_output = await self.mcp.call_tool(tool_name, tool_args)
        except Exception as e:
            logger.exception("MCP tool execution error for %s: %s", tool_name, e)
            tool_output = {"error": str(e)}

        timer.mark("tool_ms", timer._start + t1 / 1000.0)
        yield Event(type="tool_result", data={"name": tool_name, "result": tool_output})

        if tool_name == "diagnose_slowness" and isinstance(tool_output, dict):
            self.latest_findings = tool_output
            session.last_tool_result = tool_output
        elif tool_name == "propose_close" and isinstance(tool_output, dict):
            if not tool_output.get("refused"):
                session.pending_proposal = tool_output
                self.pending_proposal = tool_output
                yield Event(type="proposal", data=tool_output)
        elif isinstance(tool_output, dict):
            if "recommendations" in tool_output:
                yield Event(type="sources", data={"recommendations": tool_output["recommendations"]})
            elif "results" in tool_output:
                yield Event(type="sources", data={"results": tool_output["results"]})
            elif "citation" in tool_output:
                yield Event(type="sources", data={"citations": [tool_output["citation"]]})

        # Keep tool output within context without breaking JSON syntax
        if isinstance(tool_output, dict):
            truncated_dict = dict(tool_output)
            if "recommendations" in truncated_dict and isinstance(truncated_dict["recommendations"], list):
                truncated_dict["recommendations"] = truncated_dict["recommendations"][:3]
            if "results" in truncated_dict and isinstance(truncated_dict["results"], list):
                truncated_dict["results"] = truncated_dict["results"][:3]
            tool_output_str = json.dumps(truncated_dict)
        else:
            tool_output_str = str(tool_output)[:2000]

        # 3. Reply Call 2
        reply_sys_prompt = get_reply_prompt(
            session.script or REPLY_STYLE, tool_name=tool_name, language=session.language
        )
        call_id = f"call_{secrets.token_hex(4)}"
        call2_messages = [
            {"role": "system", "content": reply_sys_prompt},
            *session.history,
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": call_id,
                        "type": "function",
                        "function": {"name": tool_name, "arguments": json.dumps(tool_args)},
                    }
                ],
            },
            {
                "role": "tool",
                "tool_call_id": call_id,
                "content": tool_output_str,
            },
        ]

        t2 = timer.elapsed_ms()
        try:
            call2_result = await chat(messages=call2_messages, tools=None)
        except Exception as e:
            logger.exception("LLM call 2 failed in evon path: %s", e)
            err_msg = "Kshama karein, AI service abhi uplabdh nahi hai. Kripya thodi der baad dobara koshish karein."
            yield Event(type="error", text=err_msg)
            yield Event(type="reply", text=err_msg)
            timer.flush()
            yield Event(type="done", data={"total_ms": timer.total_ms})
            return

        timer.mark("llm2_ms", timer._start + t2 / 1000.0)
        reply_text = call2_result.content

        # Runtime Grounding Check (Numbers & Citations per §4.5, §6.4)
        if isinstance(tool_output, dict):
            num_valid, invalid_nums = verify_reply_numbers(reply_text, tool_output)
            cite_valid, invalid_urls = verify_reply_citations(reply_text, tool_output)
            if not num_valid or not cite_valid:
                logger.warning(
                    "Grounding check failed (numbers=%s, urls=%s) for %s. Regenerating...",
                    invalid_nums,
                    invalid_urls,
                    tool_name,
                )
                retry_messages = [
                    *call2_messages,
                    {"role": "assistant", "content": reply_text},
                    {
                        "role": "user",
                        "content": "IMPORTANT: Use ONLY exact numbers and verified URLs present in the tool result.",
                    },
                ]
                try:
                    retry_res = await chat(messages=retry_messages, tools=None)
                    num_valid2, _ = verify_reply_numbers(retry_res.content, tool_output)
                    cite_valid2, _ = verify_reply_citations(retry_res.content, tool_output)
                    if num_valid2 and cite_valid2:
                        reply_text = retry_res.content
                    else:
                        logger.warning(
                            "Regeneration still ungrounded. Falling back to deterministic template."
                        )
                        reply_text = format_template_reply(tool_output)
                except Exception:
                    reply_text = format_template_reply(tool_output)

        guarded = apply_reply_guard(reply_text, max_words=40)
        session.add_message("assistant", guarded)

        # Educational lesson card (Teach, don't just do - Principle 1)
        from syssathi.skills import resolve_skill
        skill = resolve_skill(user_input)
        if hasattr(skill, "build_lesson_card") and isinstance(tool_output, dict):
            card = skill.build_lesson_card(tool_output)
            if card:
                yield Event(
                    type="lesson_card",
                    data={
                        "title": card.title,
                        "summary": card.summary,
                        "actionable_tip": card.actionable_tip,
                        "external_link": card.external_link,
                    },
                )

        splitter = SentenceSplitter()
        for s in splitter.push(guarded) + splitter.flush():
            yield Event(type="sentence", text=s)

        yield Event(type="reply", text=guarded)
        timer.flush()
        yield Event(type="done", data={"total_ms": timer.total_ms})

    async def handle_message(self, user_text: str) -> tuple[str, Timer]:
        """Process user message, return guarded Hinglish reply and timer."""
        timer = Timer()
        reply = ""
        async for evt in self.run_turn(self.default_session, user_text):
            if evt.type == "route":
                timer.set("route", evt.data.get("route"))
            elif evt.type == "reply":
                reply = evt.text
            elif evt.type == "done":
                for k, v in evt.data.items():
                    timer.set(k, v)
        timer.flush()
        return reply, timer

    async def approve(self, session: Session | None = None) -> dict[str, Any]:
        """Execute pending proposal via execute_action."""
        active_session = session or self.default_session
        proposal = active_session.pending_proposal or self.pending_proposal
        if not proposal:
            return {"error": "No pending proposal to approve"}

        action_id = proposal.get("action_id")
        if not action_id:
            return {"error": "Pending proposal is missing action_id"}

        result = await self.mcp.call_tool(
            "execute_action",
            {
                "action_id": action_id,
                "approval_token": self.mcp.approval_token,
            },
        )
        active_session.pending_proposal = None
        self.pending_proposal = None
        return result
