"""LLM adapter — one interface, three backends (section 3 item 4)."""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# ChatResult — returned by chat()
# ---------------------------------------------------------------------------

@dataclass
class ToolCall:
    """A tool call extracted from the LLM response."""
    name: str
    arguments: dict[str, Any]


@dataclass
class ChatResult:
    """Result of a chat() call."""
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    raw: Any = None  # backend-specific raw response


# ---------------------------------------------------------------------------
# <think> stripping (section 4)
# ---------------------------------------------------------------------------

def strip_think(text: str) -> str:
    """Remove <think>...</think> blocks from *text*.

    - Closed blocks (possibly multiple) are removed entirely.
    - An unclosed <think> drops everything from it to the end.
    """
    # First remove all closed blocks (non-greedy, handles multiple)
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    # Then handle unclosed <think>: drop from <think> to end
    idx = text.find("<think>")
    if idx != -1:
        text = text[:idx]
    return text.strip()


# ---------------------------------------------------------------------------
# Mock backend
# ---------------------------------------------------------------------------

# Keyword table for simulating tool calls
_MOCK_TOOL_TABLE: list[tuple[str, str, dict[str, Any]]] = [
    ("battery", "get_battery_report", {}),
    ("startup", "list_startup_apps", {}),
    ("ram", "get_top_processes", {"limit": 5, "sort_by": "ram"}),
]


def _mock_chat(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
) -> ChatResult:
    """Deterministic mock backend — logs [MOCK], returns Hinglish reply.

    If tools are provided and the last user message matches a keyword,
    simulates the corresponding tool call.
    """
    logger.info("[MOCK] chat called with %d messages", len(messages))

    # Get the last user message
    user_text = ""
    for msg in reversed(messages):
        if msg.get("role") == "user":
            user_text = msg.get("content", "")
            break

    user_lower = user_text.lower()

    # Check for tool-call simulation when tools are provided
    if tools:
        # "band kar" + group name → propose_close
        # Hinglish patterns: "chrome band kar do", "band kar do chrome ko"
        _HINDI_STOP = {"do", "de", "karo", "kar", "ko", "bhi", "ye", "wo", "ka"}
        band_kar_idx = user_lower.find("band kar")
        if band_kar_idx != -1:
            # Try group name BEFORE "band kar" (most common Hinglish order)
            before = user_lower[:band_kar_idx].split()
            group_name = ""
            for w in reversed(before):
                if w not in _HINDI_STOP and len(w) > 1:
                    group_name = w
                    break
            # Fallback: try AFTER "band kar[o/do/de] ..."
            if not group_name:
                after = user_lower[band_kar_idx:].split()[2:]  # skip "band" "kar*"
                for w in after:
                    if w not in _HINDI_STOP and len(w) > 1:
                        group_name = w
                        break
            if group_name:
                logger.info("[MOCK] Simulating propose_close(%s)", group_name)
                return ChatResult(
                    content="",
                    tool_calls=[ToolCall("propose_close", {"group_name": group_name})],
                )

        # Keyword table
        for keyword, tool_name, args in _MOCK_TOOL_TABLE:
            if keyword in user_lower:
                logger.info("[MOCK] Simulating tool call: %s", tool_name)
                return ChatResult(
                    content="",
                    tool_calls=[ToolCall(tool_name, dict(args))],
                )

    # Build a Hinglish reply from findings if present
    reply = _mock_reply_from_findings(messages)
    logger.info("[MOCK] Reply: %s", reply)
    return ChatResult(content=reply)


def _mock_reply_from_findings(messages: list[dict[str, Any]]) -> str:
    """Build a deterministic Hinglish reply using only numbers and data from tool results."""
    # 1. Check for groups from get_top_processes
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str) and '"groups"' in content:
            try:
                match = re.search(r"\{.*\}", content, re.DOTALL)
                if match:
                    data = json.loads(match.group())
                    groups = data.get("groups", [])
                    if groups:
                        top = groups[0]
                        return f"Top process {top['name']} hai jo {top['ram_mb']} MB RAM aur {top['cpu_pct']}% CPU le raha hai."
            except Exception:
                pass

    # 2. Check for startup apps from list_startup_apps
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str) and '"entries"' in content and '"count"' in content:
            try:
                match = re.search(r"\{.*\}", content, re.DOTALL)
                if match:
                    data = json.loads(match.group())
                    count = data.get("count", 0)
                    names = [e["name"] for e in data.get("entries", [])[:3]]
                    names_str = ", ".join(names) if names else "koi app nahi"
                    return f"Startup mein {count} apps hain: {names_str}."
            except Exception:
                pass

    # 3. Check for battery report from get_battery_report
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str) and '"charge_pct"' in content:
            try:
                match = re.search(r"\{.*\}", content, re.DOTALL)
                if match:
                    data = json.loads(match.group())
                    pct = data.get("charge_pct", 0)
                    plugged = "charging par" if data.get("plugged") else "battery par"
                    health = f", health {data.get('health_pct')}%" if "health_pct" in data else ""
                    return f"Battery {pct}% charged hai aur {plugged} hai{health}."
            except Exception:
                pass

    # 4. Look for findings JSON in messages
    findings: dict[str, Any] | None = None
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str) and '"findings"' in content:
            try:
                findings = json.loads(content)
            except (json.JSONDecodeError, TypeError):
                # Try to extract JSON from within text
                match = re.search(r"\{.*\}", content, re.DOTALL)
                if match:
                    try:
                        findings = json.loads(match.group())
                    except (json.JSONDecodeError, TypeError):
                        pass

    if not findings:
        return "Laptop theek lag raha hai, koi problem nahi dikh rahi."

    # If findings was wrapped in {"findings": ..., "proposal": ...}
    if isinstance(findings.get("findings"), dict):
        findings = findings["findings"]

    if not findings.get("findings"):
        return "Laptop theek lag raha hai, koi problem nahi dikh rahi."

    parts: list[str] = []
    f_list = findings.get("findings", [])
    top_groups = findings.get("top_groups", [])

    # Mention up to 2 findings
    for f in f_list[:2]:
        code = f.get("code", "")
        if code == "RAM_HIGH":
            ram_pct = findings.get("ram_used_pct", 0)
            if top_groups:
                g = top_groups[0]
                ram_gb = round(g["ram_mb"] / 1000, 1)
                parts.append(
                    f"RAM {ram_pct}% use ho rahi hai. "
                    f"{g['name'].capitalize()} ke {g['procs']} processes "
                    f"{ram_gb} GB le rahe hain."
                )
            else:
                parts.append(f"RAM {ram_pct}% use ho rahi hai.")
        elif code == "CPU_HIGH":
            cpu_pct = findings.get("cpu_avg_pct", 0)
            parts.append(f"CPU {cpu_pct}% average hai.")
        elif code == "DISK_LOW":
            disk_pct = findings.get("disk_free_pct", 0)
            parts.append(f"Disk mein sirf {disk_pct}% jagah bachi hai.")
        elif code == "STARTUP_HIGH":
            count = findings.get("startup_apps", 0)
            parts.append(f"Startup mein {count} apps hain.")

    if not parts:
        return "Laptop theek lag raha hai, koi problem nahi dikh rahi."

    reply = " ".join(parts)
    # Enforce 40-word limit
    words = reply.split()
    if len(words) > 40:
        reply = " ".join(words[:40])
    return reply


# ---------------------------------------------------------------------------
# Evon remote backend (section 4)
# ---------------------------------------------------------------------------

def _evon_remote_chat(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
) -> ChatResult:
    """Call the Evon endpoint using the openai package."""
    from syssathi.host.config import EVON_BASE_URL, EVON_MODEL, HF_TOKEN

    import openai

    client = openai.OpenAI(
        base_url=EVON_BASE_URL,
        api_key=HF_TOKEN,
        timeout=30.0,
        max_retries=1,
    )

    # Resolve model id
    model = EVON_MODEL
    if not model:
        try:
            models = client.models.list()
            model = models.data[0].id
            logger.info("Evon model resolved to: %s", model)
        except Exception:
            logger.exception("Failed to list Evon models")
            raise

    kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": 0.6,
        "top_p": 0.95,
        "extra_body": {"chat_template_kwargs": {"enable_thinking": False}},
    }
    if tools:
        kwargs["tools"] = tools

    import time

    # Retry loop with backoff for scale-to-zero cold start
    retries = 3
    for attempt in range(retries):
        try:
            response = client.chat.completions.create(**kwargs)
            return _parse_openai_response(response)
        except Exception as e:
            err_str = str(e)
            is_503 = "503" in err_str or "Service Unavailable" in err_str
            if is_503 and attempt < retries - 1:
                wait_s = (attempt + 1) * 4
                logger.info("Evon endpoint waking up (503). Retrying in %ds (attempt %d/%d)...", wait_s, attempt + 1, retries)
                time.sleep(wait_s)
                continue

            logger.exception("Evon API call failed (%s)", e)
            logger.warning("[FALLBACK] Falling back to mock backend for resilience.")
            return _mock_chat(messages, tools)


# ---------------------------------------------------------------------------
# openai_compatible backend
# ---------------------------------------------------------------------------

def _openai_compatible_chat(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
) -> ChatResult:
    """Call any OpenAI-compatible endpoint."""
    from syssathi.host.config import (
        OPENAI_COMPAT_API_KEY,
        OPENAI_COMPAT_BASE_URL,
        OPENAI_COMPAT_MODEL,
    )

    import openai

    if not OPENAI_COMPAT_BASE_URL:
        raise RuntimeError(
            "OPENAI_COMPAT_BASE_URL is required for the openai_compatible backend"
        )

    client = openai.OpenAI(
        base_url=OPENAI_COMPAT_BASE_URL,
        api_key=OPENAI_COMPAT_API_KEY,
        timeout=30.0,
        max_retries=1,
    )

    model = OPENAI_COMPAT_MODEL
    if not model:
        try:
            models = client.models.list()
            model = models.data[0].id
            logger.info("openai_compatible model resolved to: %s", model)
        except Exception:
            logger.exception("Failed to list models from openai_compatible endpoint")
            raise

    kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": 0.6,
        "top_p": 0.95,
    }
    if tools:
        kwargs["tools"] = tools

    try:
        response = client.chat.completions.create(**kwargs)
    except Exception:
        logger.exception("openai_compatible API call failed")
        raise

    return _parse_openai_response(response)


# ---------------------------------------------------------------------------
# Shared response parser for OpenAI-format responses
# ---------------------------------------------------------------------------

def _parse_openai_response(response: Any) -> ChatResult:
    """Parse an OpenAI chat completion response into ChatResult."""
    choice = response.choices[0]
    message = choice.message

    content = message.content or ""
    content = strip_think(content)

    tool_calls: list[ToolCall] = []
    if message.tool_calls:
        for tc in message.tool_calls:
            args = tc.function.arguments
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except (json.JSONDecodeError, TypeError):
                    args = {}
            tool_calls.append(ToolCall(name=tc.function.name, arguments=args))

    return ChatResult(content=content, tool_calls=tool_calls, raw=response)


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

_BACKENDS = {
    "evon_remote": _evon_remote_chat,
    "openai_compatible": _openai_compatible_chat,
    "mock": _mock_chat,
}


def chat(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
    *,
    backend: str | None = None,
) -> ChatResult:
    """Send messages to the LLM and return a ChatResult.

    Args:
        messages: OpenAI-format message list.
        tools: Optional tool schemas (OpenAI function-calling format).
        backend: Override the configured backend (for testing).
    """
    if backend is None:
        from syssathi.host.config import LLM_BACKEND
        backend = LLM_BACKEND

    fn = _BACKENDS.get(backend)
    if fn is None:
        raise ValueError(
            f"Unknown LLM backend {backend!r}. "
            f"Choose from: {', '.join(_BACKENDS)}"
        )

    return fn(messages, tools)

