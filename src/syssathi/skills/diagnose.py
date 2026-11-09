"""Diagnose Skill — Skill #1: Laptop slowness, resource pressure, battery, and startup."""

from __future__ import annotations

from typing import Any

from syssathi.grounding import format_template_reply
from syssathi.skills.base import BaseSkill, LessonCard


class DiagnoseSkill(BaseSkill):
    """Skill diagnosing hardware and system resource slowness."""

    name = "diagnose"
    description = "Diagnoses laptop slowness, high RAM/CPU usage, battery state, and startup bloat."

    def can_handle(self, text: str, intent: str | None = None) -> bool:
        if intent in ("diagnose", "battery", "startup", "processes"):
            return True
        lower = text.lower()
        slowness_terms = [
            "slow", "hang", "lag", "laggy", "dheema", "dhima", "atak",
            "freeze", "battery", "startup", "ram", "cpu", "process",
            "धीमा", "धीमे", "अटक", "लैक", "हैंग", "बैटरी", "स्टार्टअप",
        ]
        return any(term in lower for term in slowness_terms)

    def get_tools(self) -> list[str]:
        return [
            "diagnose_slowness",
            "get_top_processes",
            "list_startup_apps",
            "get_battery_report",
            "propose_close",
        ]

    def get_system_prompt(self, language: str = "hi", script: str = "latin") -> str:
        if script == "devanagari":
            return (
                "You are SysSathi (सिस्सार्थी), a helpful multilingual system companion for Windows. "
                "Explain the diagnostic findings clearly, calmly, and simply in Hindi using Devanagari script. "
                "Teach the user with a simple real-world analogy (RAM is like a study desk, CPU like an engine). "
                "Always state the exact measured numbers and suggest closing heavy non-critical apps. "
                "Never exceed 40 words. End with a complete sentence."
            )
        elif language == "en":
            return (
                "You are SysSathi, a friendly technology companion for Windows. "
                "Explain the diagnostic findings clearly in simple English without jargon. "
                "State the exact measured numbers and offer a safe fix. "
                "Never exceed 40 words. End with a complete sentence."
            )
        else:
            return (
                "You are SysSathi, a helpful system companion for Windows. "
                "Explain the diagnostic findings in natural Hinglish (Hindi written in Roman letters). "
                "Use simple language: state the exact numbers (e.g. RAM 91%), explain why the laptop is slow, "
                "and propose a fix. Never exceed 40 words. End with a complete sentence."
            )

    def build_lesson_card(self, findings: dict[str, Any]) -> LessonCard | None:
        """Create a teachable lesson card from diagnostic findings (Principle 1)."""
        if not isinstance(findings, dict):
            return None
        finding_codes = {f.get("code") for f in findings.get("findings", [])}

        if "RAM_HIGH" in finding_codes:
            return LessonCard(
                title="What is RAM? (रैम क्या है?)",
                summary="RAM is like your desk space. The more open apps you have on your desk, the less room there is to work smoothly.",
                actionable_tip="Press Ctrl + Shift + Esc on Windows to see which apps are using your desk space.",
            )
        if "CPU_HIGH" in finding_codes:
            return LessonCard(
                title="What is CPU? (प्रोसेसर क्या है?)",
                summary="The CPU is your computer's engine. When too many heavy processes run simultaneously, the engine works overtime causing stutter.",
                actionable_tip="Check Task Manager to see which processes are demanding high CPU percentage.",
            )
        if "STARTUP_HIGH" in finding_codes:
            return LessonCard(
                title="Startup Apps (स्टार्टअप ऐप्स)",
                summary="Apps that silently start every time you turn on your PC slow down your boot time and idle memory.",
                actionable_tip="Open Task Manager -> Startup tab and disable apps you only use occasionally.",
            )
        return None

    def format_deterministic_fallback(
        self, tool_output: dict[str, Any], language: str = "hi"
    ) -> str:
        return format_template_reply(tool_output)

