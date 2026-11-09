"""SysSathi Skills registry and exports (§5.2)."""

from syssathi.skills.base import BaseSkill, LessonCard, SkillResult
from syssathi.skills.diagnose import DiagnoseSkill
from syssathi.skills.errors import ErrorExplainerSkill
from syssathi.skills.explain import ExplainSkill
from syssathi.skills.howto import HowToSkill
from syssathi.skills.toolfinder import ToolFinderSkill

ALL_SKILLS: list[BaseSkill] = [
    DiagnoseSkill(),
    ExplainSkill(),
    ToolFinderSkill(),
    HowToSkill(),
    ErrorExplainerSkill(),
]


def resolve_skill(text: str, intent: str | None = None) -> BaseSkill:
    """Find the best skill for a user query, defaulting to DiagnoseSkill."""
    for skill in ALL_SKILLS:
        if skill.can_handle(text, intent):
            return skill
    return ALL_SKILLS[0]  # default to diagnose


__all__ = [
    "BaseSkill",
    "LessonCard",
    "SkillResult",
    "DiagnoseSkill",
    "ExplainSkill",
    "ToolFinderSkill",
    "HowToSkill",
    "ErrorExplainerSkill",
    "ALL_SKILLS",
    "resolve_skill",
]

