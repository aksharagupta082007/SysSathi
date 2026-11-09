"""Tool Finder Skill — Recommends curated tools and software with download safety guidance (§5.1)."""

from __future__ import annotations

from typing import Any

from syssathi.grounding import format_template_reply
from syssathi.skills.base import BaseSkill, LessonCard


class ToolFinderSkill(BaseSkill):
    """Recommends safe, free, open-source or trusted software tools grounded in FMHY/directories."""

    name = "toolfinder"
    description = "Finds recommended software tools (photo editors, media players, utilities) with risk context."

    def can_handle(self, text: str, intent: str | None = None) -> bool:
        if intent == "toolfinder":
            return True
        lower = text.lower()
        tool_keywords = [
            "software", "app", "tool", "free mein", "download", "alternative",
            "photo edit", "video edit", "convert", "compress", "torrent",
        ]
        return any(k in lower for k in tool_keywords)

    def get_tools(self) -> list[str]:
        return ["get_tool_recommendations", "search_sources"]

    def get_system_prompt(self, language: str = "hi", script: str = "latin") -> str:
        return (
            "You are SysSathi, a technology companion guiding users to safe, trustworthy software. "
            "Suggest well-vetted tools from curated community catalogs (FMHY). Always attach download safety advice "
            "(check official domain, verify publisher, beware ad download buttons). Keep it under 40 words."
        )

    def build_lesson_card(self, tool_output: dict[str, Any]) -> LessonCard | None:
        """Create a download safety LessonCard from tool recommendations."""
        recs = tool_output.get("recommendations", [])
        if recs:
            top_rec = recs[0]
            tip = (
                top_rec["download_safety_tips"][0]
                if top_rec.get("download_safety_tips")
                else "Scan installer with Windows Defender before running."
            )
            return LessonCard(
                title=f"Download Safety: {top_rec.get('name')}",
                summary=f"Recommended tool: {top_rec.get('name')} ({top_rec.get('why_recommended')})",
                actionable_tip=tip,
                external_link=top_rec.get("url"),
            )
        return None

    def format_deterministic_fallback(
        self, tool_output: dict[str, Any], language: str = "hi"
    ) -> str:
        return format_template_reply(tool_output)
