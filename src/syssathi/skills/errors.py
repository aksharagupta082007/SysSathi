"""Error Explainer Skill — Translates cryptic error codes into plain language (§5.1)."""

from __future__ import annotations

import re
from typing import Any

from syssathi.grounding import format_template_reply
from syssathi.skills.base import BaseSkill, LessonCard


class ErrorExplainerSkill(BaseSkill):
    """Explains Windows and software error codes (e.g. 0x80070005, BSOD codes)."""

    name = "errors"
    description = "Decodes Windows error codes, permission denials, and update failures into plain explanations."

    def can_handle(self, text: str, intent: str | None = None) -> bool:
        if intent == "errors":
            return True
        lower = text.lower()
        if "error" in lower or "code" in lower:
            return True
        # Check for hex error pattern like 0x80070005
        if re.search(r"0x[0-9a-fA-F]{4,8}", text):
            return True
        return False

    def get_tools(self) -> list[str]:
        return ["explain_term", "search_sources"]

    def get_system_prompt(self, language: str = "hi", script: str = "latin") -> str:
        return (
            "You are SysSathi. Explain the Windows error code in simple language: "
            "what went wrong (e.g. Access Denied, Disk Full, Corrupted File) and how to resolve it safely. "
            "Never tell the user to download untrusted DLL fixers."
        )

    def build_lesson_card(self, tool_output: dict[str, Any]) -> LessonCard | None:
        """Create a troubleshooting LessonCard from error explanation output."""
        if "title" in tool_output and "summary" in tool_output:
            link = tool_output.get("citation", {}).get("url")
            return LessonCard(
                title=f"Fix: {tool_output['title']}",
                summary=tool_output["summary"],
                actionable_tip=tool_output.get("detailed_explanation", "")[:120] + "...",
                external_link=link,
            )
        results = tool_output.get("results", [])
        if results:
            top = results[0]
            return LessonCard(
                title=f"Fix: {top.get('title')}",
                summary=top.get("summary", ""),
                actionable_tip=top.get("content", "")[:120] + "...",
                external_link=top.get("url"),
            )
        return None

    def format_deterministic_fallback(
        self, tool_output: dict[str, Any], language: str = "hi"
    ) -> str:
        return format_template_reply(tool_output)
