"""How-To Skill — Step-by-step guidance adapted to user's operating system (§5.1)."""

from __future__ import annotations

from typing import Any

from syssathi.grounding import format_template_reply
from syssathi.skills.base import BaseSkill, LessonCard


class HowToSkill(BaseSkill):
    """Provides actionable, step-by-step instructions for common system tasks."""

    name = "howto"
    description = "Provides step-by-step how-to guidance (changing wifi password, screenshot, clearing cache)."

    def can_handle(self, text: str, intent: str | None = None) -> bool:
        if intent == "howto":
            return True
        lower = text.lower()
        howto_keywords = [
            "kaise karein", "kaise karu", "kaise badlu", "how to", "steps to",
            "kaise", "how do i", "কিভাবে", "எப்படி", "ఎలా", "change wifi", "screenshot",
        ]
        return any(k in lower for k in howto_keywords)

    def get_tools(self) -> list[str]:
        return ["search_sources"]

    def get_system_prompt(self, language: str = "hi", script: str = "latin") -> str:
        return (
            "You are SysSathi, giving crisp step-by-step instructions for Windows tasks. "
            "Number each step (1, 2, 3), use exact button or key names, and keep instructions concise."
        )

    def build_lesson_card(self, tool_output: dict[str, Any]) -> LessonCard | None:
        """Create a step-by-step guide LessonCard from how-to search results."""
        results = tool_output.get("results", [])
        if results:
            top = results[0]
            return LessonCard(
                title=f"Guide: {top.get('title')}",
                summary=top.get("summary", ""),
                actionable_tip=top.get("content", "")[:120] + "...",
                external_link=top.get("url"),
            )
        return None

    def format_deterministic_fallback(
        self, tool_output: dict[str, Any], language: str = "hi"
    ) -> str:
        return format_template_reply(tool_output)
