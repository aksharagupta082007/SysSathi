"""Source registry and license verification (Phase D §6.1)."""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


class SourceTrust(str, Enum):
    """Trust tier of a knowledge source."""

    COMMUNITY = "community"
    ENCYCLOPEDIC = "encyclopedic"
    OFFICIAL = "official"
    UNVERIFIED = "unverified"


class SourceIngestType(str, Enum):
    """Method used to ingest the source."""

    GIT = "git"
    API = "api"
    FILE = "file"


class SourceConfig(BaseModel):
    """Configuration and license metadata for a curated knowledge source."""

    id: str
    name: str
    homepage: str
    ingest: SourceIngestType
    repo: str | None = None
    license: str
    trust: SourceTrust
    refresh: str | None = None
    include_sections: str = "all"
    description: str = ""

    def is_permissive_or_open(self) -> bool:
        """Check whether the license permits local indexing and distribution."""
        open_licenses = {
            "CC0-1.0",
            "CC-BY-4.0",
            "CC-BY-SA-4.0",
            "CC-BY-3.0",
            "MIT",
            "Apache-2.0",
            "Open-Documentation",
        }
        return self.license in open_licenses


class SourceRegistry(BaseModel):
    """Registry holding all configured knowledge sources."""

    sources: dict[str, SourceConfig] = Field(default_factory=dict)

    def get(self, source_id: str) -> SourceConfig | None:
        """Get source by id."""
        return self.sources.get(source_id)

    def list_sources(self) -> list[SourceConfig]:
        """List all registered sources."""
        return list(self.sources.values())

    def verify_all_licenses(self) -> dict[str, bool]:
        """Verify license suitability for all registered sources."""
        return {src.id: src.is_permissive_or_open() for src in self.sources.values()}

    @classmethod
    def load_from_yaml(cls, path: Path | None = None) -> SourceRegistry:
        """Load sources registry from sources.yaml."""
        if path is None:
            path = Path(__file__).parent / "sources.yaml"

        if not path.exists():
            return cls(sources={})

        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        raw_sources = data.get("sources", {})
        parsed: dict[str, SourceConfig] = {}
        for src_id, src_dict in raw_sources.items():
            if isinstance(src_dict, dict):
                src_dict.setdefault("id", src_id)
                parsed[src_id] = SourceConfig(**src_dict)

        return cls(sources=parsed)


# Cached singleton registry
_GLOBAL_REGISTRY: SourceRegistry | None = None


def get_source_registry() -> SourceRegistry:
    """Return the global source registry instance."""
    global _GLOBAL_REGISTRY
    if _GLOBAL_REGISTRY is None:
        _GLOBAL_REGISTRY = SourceRegistry.load_from_yaml()
    return _GLOBAL_REGISTRY

