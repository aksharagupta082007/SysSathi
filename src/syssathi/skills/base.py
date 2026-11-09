"""Base skill contract and lesson card models (Phase C §5.1, §5.2)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class LessonCard:
    """Educational card teaching the user a technology concept (Teach, don't just do)."""

    title: str
    summary: str
    actionable_tip: str = ""
    external_link: str | None = None


@dataclass
class SkillResult:
    """Standardized output from a skill execution."""

    skill_name: str
    reply_text: str
    lesson_card: LessonCard | None = None
    proposal: dict[str, Any] | None = None
    sources: list[dict[str, Any]] = field(default_factory=list)
    raw_data: dict[str, Any] = field(default_factory=dict)


class BaseSkill(ABC):
    """Abstract base class for all SysSathi skills."""

    name: str
    description: str

    @abstractmethod
    def can_handle(self, text: str, intent: str | None = None) -> bool:
        """Return True if this skill can address the user query."""
        pass

    @abstractmethod
    def get_system_prompt(self, language: str = "hi", script: str = "latin") -> str:
        """Return the skill's system prompt adapted to language/script."""
        pass

    @abstractmethod
    def get_tools(self) -> list[str]:
        """Return list of MCP tool names used by this skill."""
        pass

    @abstractmethod
    def format_deterministic_fallback(
        self, tool_output: dict[str, Any], language: str = "hi"
    ) -> str:
        """Return deterministic template reply if LLM is unavailable."""
        pass

