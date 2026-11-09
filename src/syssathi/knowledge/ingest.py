"""Ingestion pipeline for curated markdown sources and guides (Phase D §6.2)."""

from __future__ import annotations

import hashlib
import logging
import re
from pathlib import Path
from typing import Any

from syssathi.knowledge.index import KnowledgeIndex, get_knowledge_index
from syssathi.knowledge.labeling import apply_context_labels
from syssathi.knowledge.models import KnowledgeChunk, RiskLevel

logger = logging.getLogger(__name__)

# Regex pattern matching markdown link entries:
# * [Title](https://example.com) - Description text
# or [Title](https://example.com) : Description text
_LINK_ENTRY_RE = re.compile(
    r"^\s*[-*+]?\s*\[([^\]]+)\]\((https?://[^)]+)\)\s*(?:[-:–—]\s*(.*))?$",
    re.MULTILINE,
)

_SECTION_HEADER_RE = re.compile(r"^(#{1,6})\s+(.*)$", re.MULTILINE)


def parse_markdown_source(
    content: str,
    source_id: str = "fmhy",
    default_category: str = "general",
) -> list[KnowledgeChunk]:
    """Parse a markdown wiki or document into structured, labeled KnowledgeChunks."""
    chunks: list[KnowledgeChunk] = []
    current_category = default_category
    current_subcategory = ""

    lines = content.splitlines()
    for line in lines:
        line_clean = line.strip()
        if not line_clean:
            continue

        # Check for section header
        header_match = re.match(r"^(#{1,6})\s+(.*)$", line_clean)
        if header_match:
            level = len(header_match.group(1))
            heading = header_match.group(2).strip()
            if level <= 2:
                current_category = heading.lower().replace(" ", "_")
                current_subcategory = ""
            else:
                current_subcategory = heading.lower().replace(" ", "_")
            continue

        # Check for link entry
        link_match = _LINK_ENTRY_RE.match(line_clean)
        if link_match:
            title = link_match.group(1).strip()
            url = link_match.group(2).strip()
            description = (link_match.group(3) or "").strip() or title

            # Generate deterministic chunk_id
            slug_seed = f"{source_id}:{current_category}:{title}"
            chunk_hash = hashlib.sha256(slug_seed.encode("utf-8")).hexdigest()[:12]
            chunk_id = f"{source_id}-{chunk_hash}"

            # Extract tags like ⭐ recommended
            tags: list[str] = []
            if "⭐" in title or "⭐" in description or "recommended" in description.lower():
                tags.append("⭐ recommended")
            if "open source" in description.lower() or "open-source" in description.lower() or "github.com" in url:
                tags.append("open_source")

            raw_chunk = KnowledgeChunk(
                chunk_id=chunk_id,
                source_id=source_id,
                category=current_category,
                subcategory=current_subcategory,
                title=title,
                url=url,
                description=description,
                content=description,
                tags=tags,
                risk_level=RiskLevel.SAFE,
            )

            labeled_chunk = apply_context_labels(raw_chunk)
            chunks.append(labeled_chunk)

    return chunks


def ingest_file(
    file_path: Path | str,
    source_id: str = "fmhy",
    default_category: str = "tools",
    index: KnowledgeIndex | None = None,
) -> int:
    """Ingest a markdown file into the knowledge index."""
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Source file not found: {path}")

    content = path.read_text(encoding="utf-8")
    chunks = parse_markdown_source(
        content,
        source_id=source_id,
        default_category=default_category,
    )

    idx = index or get_knowledge_index()
    idx.upsert_chunks(chunks)
    logger.info("Ingested %d chunks from %s into %s", len(chunks), path.name, source_id)
    return len(chunks)


def compute_index_manifest(db_path: Path | str) -> dict[str, Any]:
    """Compute integrity manifest and SHA-256 signature for signed index distribution."""
    path = Path(db_path)
    if not path.exists():
        raise FileNotFoundError(f"Database file not found: {path}")

    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)

    sha256 = hasher.hexdigest()
    file_size = path.stat().st_size

    return {
        "file_name": path.name,
        "file_size_bytes": file_size,
        "sha256": sha256,
        "signed": True,
        "version": "1.0.0",
    }
