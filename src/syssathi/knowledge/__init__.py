"""SysSathi Knowledge subsystem (Phase D).

Curated knowledge sources, SQLite FTS5 local index, context labeling, and citations.
"""

from syssathi.knowledge.index import KnowledgeIndex, get_knowledge_index
from syssathi.knowledge.ingest import compute_index_manifest, ingest_file, parse_markdown_source
from syssathi.knowledge.labeling import apply_context_labels, build_tool_recommendation
from syssathi.knowledge.models import Citation, KnowledgeChunk, RiskLevel, ToolRecommendation
from syssathi.knowledge.sources import SourceConfig, SourceRegistry, SourceTrust, get_source_registry

__all__ = [
    "KnowledgeIndex",
    "get_knowledge_index",
    "ingest_file",
    "parse_markdown_source",
    "compute_index_manifest",
    "apply_context_labels",
    "build_tool_recommendation",
    "KnowledgeChunk",
    "ToolRecommendation",
    "Citation",
    "RiskLevel",
    "SourceConfig",
    "SourceRegistry",
    "SourceTrust",
    "get_source_registry",
]

