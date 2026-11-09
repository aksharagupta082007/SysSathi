"""SQLite FTS5 knowledge index and search engine (Phase D §6.2, §6.3)."""

from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path
from typing import Any

from platformdirs import user_data_dir

from syssathi.knowledge.labeling import apply_context_labels, build_tool_recommendation
from syssathi.knowledge.models import Citation, KnowledgeChunk, RiskLevel, ToolRecommendation
from syssathi.knowledge.seeds import DEFAULT_KNOWLEDGE_SEEDS

logger = logging.getLogger(__name__)


def _sanitize_fts_query(query: str) -> str:
    """Sanitize user query for SQLite FTS5 syntax."""
    # Strip special FTS5 operators like quotes, asterisks, brackets
    cleaned = "".join(ch if ch.isalnum() or ch.isspace() else " " for ch in query)
    tokens = [t.strip() for t in cleaned.split() if t.strip()]
    if not tokens:
        return ""
    # Search each token with prefix matching: token1* OR token2*
    return " OR ".join(f'"{t}"*' for t in tokens)


class KnowledgeIndex:
    """Local SQLite FTS5 knowledge index for offline, sub-millisecond retrieval."""

    def __init__(self, db_path: Path | str | None = None) -> None:
        if db_path is None:
            base_dir = Path(user_data_dir("syssathi", appauthor=False))
            base_dir.mkdir(parents=True, exist_ok=True)
            self.db_path = base_dir / "knowledge.db"
        elif str(db_path) == ":memory:":
            self.db_path = ":memory:"
        else:
            self.db_path = Path(db_path)
            if self.db_path.parent:
                self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self._conn = sqlite3.connect(
            str(self.db_path),
            check_same_thread=False,
            autocommit=True,
        )
        self._init_schema()
        self._seed_if_empty()

    def _init_schema(self) -> None:
        """Create tables and FTS5 virtual tables."""
        with self._conn:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS chunks (
                    chunk_id TEXT PRIMARY KEY,
                    source_id TEXT NOT NULL,
                    category TEXT NOT NULL,
                    subcategory TEXT,
                    title TEXT NOT NULL,
                    url TEXT,
                    description TEXT NOT NULL,
                    content TEXT,
                    context_notes TEXT,
                    risk_level TEXT NOT NULL,
                    legal_note TEXT,
                    tags TEXT,
                    os_support TEXT,
                    version TEXT
                );
                """
            )
            self._conn.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
                    chunk_id UNINDEXED,
                    source_id,
                    category,
                    title,
                    description,
                    content,
                    tags,
                    tokenize = 'unicode61'
                );
                """
            )

    def _seed_if_empty(self) -> None:
        """Seed default knowledge base if the table is currently empty."""
        cursor = self._conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM chunks")
        count = cursor.fetchone()[0]
        if count == 0:
            logger.info("Knowledge base is empty. Seeding %d curated chunks...", len(DEFAULT_KNOWLEDGE_SEEDS))
            self.upsert_chunks(DEFAULT_KNOWLEDGE_SEEDS)

    def upsert_chunks(self, chunks: list[KnowledgeChunk]) -> None:
        """Insert or replace knowledge chunks with automatic context labeling."""
        with self._conn:
            for raw_chunk in chunks:
                chunk = apply_context_labels(raw_chunk)
                tags_str = " ".join(chunk.tags)

                self._conn.execute(
                    """
                    INSERT OR REPLACE INTO chunks (
                        chunk_id, source_id, category, subcategory, title, url,
                        description, content, context_notes, risk_level,
                        legal_note, tags, os_support, version
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        chunk.chunk_id,
                        chunk.source_id,
                        chunk.category,
                        chunk.subcategory,
                        chunk.title,
                        chunk.url,
                        chunk.description,
                        chunk.content,
                        json.dumps(chunk.context_notes),
                        chunk.risk_level.value,
                        chunk.legal_note,
                        json.dumps(chunk.tags),
                        json.dumps(chunk.os_support),
                        chunk.version,
                    ),
                )

                # Update FTS5 index
                self._conn.execute(
                    "DELETE FROM chunks_fts WHERE chunk_id = ?;", (chunk.chunk_id,)
                )
                self._conn.execute(
                    """
                    INSERT INTO chunks_fts (
                        chunk_id, source_id, category, title, description, content, tags
                    ) VALUES (?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        chunk.chunk_id,
                        chunk.source_id,
                        chunk.category,
                        chunk.title,
                        chunk.description,
                        chunk.content,
                        tags_str,
                    ),
                )

    def _row_to_chunk(self, row: tuple[Any, ...]) -> KnowledgeChunk:
        """Convert a database row into a typed KnowledgeChunk."""
        (
            chunk_id,
            source_id,
            category,
            subcategory,
            title,
            url,
            description,
            content,
            context_notes_json,
            risk_level,
            legal_note,
            tags_json,
            os_support_json,
            version,
        ) = row

        return KnowledgeChunk(
            chunk_id=chunk_id,
            source_id=source_id,
            category=category,
            subcategory=subcategory or "",
            title=title,
            url=url or "",
            description=description,
            content=content or "",
            context_notes=json.loads(context_notes_json or "[]"),
            risk_level=RiskLevel(risk_level),
            legal_note=legal_note or "",
            tags=json.loads(tags_json or "[]"),
            os_support=json.loads(os_support_json or '["windows"]'),
            version=version or "1.0",
        )

    def search_sources(
        self,
        query: str,
        lang: str = "en",
        k: int = 5,
        source_ids: list[str] | None = None,
    ) -> list[KnowledgeChunk]:
        """Search curated sources using FTS5 BM25 ranking with LIKE fallback."""
        if not query.strip():
            return []

        fts_query = _sanitize_fts_query(query)
        chunks: list[KnowledgeChunk] = []

        if fts_query:
            try:
                cursor = self._conn.cursor()
                cursor.execute(
                    """
                    SELECT c.chunk_id, c.source_id, c.category, c.subcategory, c.title, c.url,
                           c.description, c.content, c.context_notes, c.risk_level,
                           c.legal_note, c.tags, c.os_support, c.version
                    FROM chunks_fts f
                    JOIN chunks c ON f.chunk_id = c.chunk_id
                    WHERE chunks_fts MATCH ?
                    ORDER BY bm25(chunks_fts) ASC
                    LIMIT ?;
                    """,
                    (fts_query, k * 2),
                )
                rows = cursor.fetchall()
                for row in rows:
                    ch = self._row_to_chunk(row)
                    if source_ids is None or ch.source_id in source_ids:
                        chunks.append(ch)
                        if len(chunks) >= k:
                            break
            except Exception as e:
                logger.warning("FTS search encountered error: %s", e)

        # Fallback to substring LIKE search if FTS yielded few results
        if len(chunks) < k:
            seen_ids = {c.chunk_id for c in chunks}
            cursor = self._conn.cursor()
            pattern = f"%{query.strip()}%"
            cursor.execute(
                """
                SELECT chunk_id, source_id, category, subcategory, title, url,
                       description, content, context_notes, risk_level,
                       legal_note, tags, os_support, version
                FROM chunks
                WHERE title LIKE ? OR description LIKE ? OR content LIKE ?
                LIMIT ?;
                """,
                (pattern, pattern, pattern, k),
            )
            for row in cursor.fetchall():
                ch = self._row_to_chunk(row)
                if ch.chunk_id not in seen_ids and (source_ids is None or ch.source_id in source_ids):
                    chunks.append(ch)
                    seen_ids.add(ch.chunk_id)
                    if len(chunks) >= k:
                        break

        return chunks

    def get_tool_recommendations(
        self,
        need: str,
        os_name: str = "windows",
        lang: str = "en",
        k: int = 5,
    ) -> list[ToolRecommendation]:
        """Find curated software recommendations matching user need."""
        chunks = self.search_sources(query=need, lang=lang, k=k * 2)

        recommendations: list[ToolRecommendation] = []
        for ch in chunks:
            # Check OS compatibility
            if os_name.lower() in [o.lower() for o in ch.os_support]:
                # Exclude purely conceptual articles from tool recommendation list
                if not ch.category.startswith("concept_") and not ch.category.startswith("howto_"):
                    recommendations.append(build_tool_recommendation(ch))
                    if len(recommendations) >= k:
                        break

        return recommendations

    def explain_term(
        self,
        term: str,
        lang: str = "en",
        level: str = "beginner",
    ) -> dict[str, Any]:
        """Provide grounded explanation and citations for a computing term or error code."""
        # 1. First search for direct concept or error match
        results = self.search_sources(query=term, lang=lang, k=3)
        if not results:
            return {
                "term": term,
                "found": False,
                "explanation": f"'{term}' par koi direct source entry nahi mili.",
                "citations": [],
            }

        top_chunk = results[0]
        citation = Citation(
            source_id=top_chunk.source_id,
            title=top_chunk.title,
            url=top_chunk.url,
            snippet=top_chunk.description,
            trust="encyclopedic" if top_chunk.source_id == "wikipedia" else "official",
        )

        return {
            "term": term,
            "found": True,
            "title": top_chunk.title,
            "summary": top_chunk.description,
            "detailed_explanation": top_chunk.content,
            "risk_level": top_chunk.risk_level.value,
            "context_notes": top_chunk.context_notes,
            "legal_note": top_chunk.legal_note,
            "citation": citation.model_dump(),
        }

    def verify_index_integrity(self) -> bool:
        """Verify that the database and FTS5 tables are intact and non-empty."""
        try:
            cursor = self._conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM chunks")
            count = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM chunks_fts")
            fts_count = cursor.fetchone()[0]
            return count > 0 and count == fts_count
        except Exception as e:
            logger.error("Index integrity check failed: %s", e)
            return False

    def close(self) -> None:
        """Close SQLite database connection."""
        self._conn.close()


# Cached singleton index instance
_GLOBAL_INDEX: KnowledgeIndex | None = None


def get_knowledge_index() -> KnowledgeIndex:
    """Return the global KnowledgeIndex instance."""
    global _GLOBAL_INDEX
    if _GLOBAL_INDEX is None:
        _GLOBAL_INDEX = KnowledgeIndex()
    return _GLOBAL_INDEX

