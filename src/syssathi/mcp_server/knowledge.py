"""Knowledge MCP tools (Phase D §6.4).

Provides read-only access to curated sources (FMHY, Wikipedia, Microsoft Learn, EFF SSD).
"""

from __future__ import annotations

import logging
from typing import Any

from syssathi.knowledge.index import get_knowledge_index

logger = logging.getLogger(__name__)


def search_sources(
    query: str,
    lang: str = "en",
    k: int = 5,
    source_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Search curated tech and software sources (FMHY, Wikipedia, MS Learn, EFF)."""
    idx = get_knowledge_index()
    chunks = idx.search_sources(query=query, lang=lang, k=k, source_ids=source_ids)

    return {
        "query": query,
        "count": len(chunks),
        "results": [
            {
                "chunk_id": c.chunk_id,
                "source": c.source_id,
                "title": c.title,
                "url": c.url,
                "summary": c.description,
                "content": c.content,
                "risk_level": c.risk_level.value,
                "legal_note": c.legal_note,
                "context_notes": c.context_notes,
                "tags": c.tags,
            }
            for c in chunks
        ],
    }


def get_tool_recommendations(
    need: str,
    os_name: str = "windows",
    lang: str = "en",
) -> dict[str, Any]:
    """Get curated software recommendations with download safety tips and risk notes."""
    idx = get_knowledge_index()
    recs = idx.get_tool_recommendations(need=need, os_name=os_name, lang=lang, k=5)

    return {
        "need": need,
        "os": os_name,
        "count": len(recs),
        "recommendations": [
            {
                "name": r.name,
                "url": r.url,
                "category": r.category,
                "why_recommended": r.why_recommended,
                "risk_level": r.risk_level.value,
                "download_safety_tips": r.download_safety_tips,
                "context_notes": r.context_notes,
                "legal_note": r.legal_note,
                "source": r.source,
                "tags": r.tags,
            }
            for r in recs
        ],
    }


def explain_term(
    term: str,
    lang: str = "en",
    level: str = "beginner",
) -> dict[str, Any]:
    """Look up an encyclopedic or troubleshooting explanation for a tech term or error."""
    idx = get_knowledge_index()
    return idx.explain_term(term=term, lang=lang, level=level)

