"""Knowledge data models (Phase D §6.2, §6.3)."""

from __future__ import annotations

from enum import Enum
from typing import Any
from pydantic import BaseModel, Field


class RiskLevel(str, Enum):
    """Risk tier for recommended tools and knowledge chunks."""

    SAFE = "safe"
    CAUTION = "caution"
    HIGH_RISK = "high_risk"


class KnowledgeChunk(BaseModel):
    """An atomic chunk of knowledge stored in the local index."""

    chunk_id: str
    source_id: str
    category: str
    subcategory: str = ""
    title: str
    url: str = ""
    description: str
    content: str = ""
    context_notes: list[str] = Field(default_factory=list)
    risk_level: RiskLevel = RiskLevel.SAFE
    legal_note: str = ""
    tags: list[str] = Field(default_factory=list)
    os_support: list[str] = Field(default_factory=lambda: ["windows"])
    version: str = "1.0"


class ToolRecommendation(BaseModel):
    """Structured software or tool recommendation (Decision 3: Educate, don't block)."""

    name: str
    url: str
    category: str
    why_recommended: str
    risk_level: RiskLevel = RiskLevel.SAFE
    context_notes: list[str] = Field(default_factory=list)
    legal_note: str = ""
    tags: list[str] = Field(default_factory=list)
    download_safety_tips: list[str] = Field(default_factory=list)
    source: str = "fmhy"


class Citation(BaseModel):
    """Citation referencing a verified curated source."""

    source_id: str
    title: str
    url: str
    snippet: str = ""
    trust: str = "community"

