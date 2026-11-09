"""Explain Skill — Concept explanation grounded in curated sources (§5.1)."""

from __future__ import annotations

from typing import Any

from syssathi.grounding import format_template_reply
from syssathi.skills.base import BaseSkill, LessonCard


class ExplainSkill(BaseSkill):
    """Answers technology questions with plain-language explanations and safety warnings."""

    name = "explain"
    description = "Explains technology concepts (VPN, DNS, malware, encryption, open source) grounded in sources."

    def can_handle(self, text: str, intent: str | None = None) -> bool:
        if intent == "explain":
            return True
        lower = text.lower()
        explain_keywords = [
            "kya hota hai", "kya hai", "what is", "explain", "samjhao", "meaning",
            "vpn", "malware", "dns", "firewall", "cookie", "cache", "phishing",
            "কি", "என்ன", "ఏమిటి", "काय आहे",
        ]
        return any(k in lower for k in explain_keywords)

    def get_tools(self) -> list[str]:
        return ["explain_term", "search_sources"]

    def get_system_prompt(self, language: str = "hi", script: str = "latin") -> str:
        return (
            "You are SysSathi, an educational technology companion. "
            "Explain the technical concept in simple, everyday terms with a relatable analogy. "
            "Always include safety or privacy warnings if relevant. Citing sources is mandatory. "
            "Keep the reply concise (under 40 words) and accessible to first-time computer users."
        )

    def build_lesson_card(self, tool_output: dict[str, Any]) -> LessonCard | None:
        """Create an educational LessonCard from explanation output."""
        if "title" in tool_output and "summary" in tool_output:
            link = tool_output.get("citation", {}).get("url")
            notes = tool_output.get("context_notes", [])
            tip = notes[0] if notes else "Learn more on Wikipedia or official docs."
            return LessonCard(
                title=f"Learn: {tool_output['title']}",
                summary=tool_output["summary"],
                actionable_tip=tip,
                external_link=link,
            )
        return None

    def format_deterministic_fallback(
        self, tool_output: dict[str, Any], language: str = "hi"
    ) -> str:
        return format_template_reply(tool_output)
