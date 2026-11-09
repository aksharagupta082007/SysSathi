"""Tests for Knowledge sources, FTS5 index, context labeling, and citations (Phase D)."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

import pytest

from syssathi.grounding import (
    collect_allowed_urls,
    extract_urls_from_text,
    format_template_reply,
    verify_reply_citations,
)
from syssathi.knowledge.index import KnowledgeIndex
from syssathi.knowledge.ingest import compute_index_manifest, parse_markdown_source
from syssathi.knowledge.labeling import apply_context_labels, build_tool_recommendation
from syssathi.knowledge.models import KnowledgeChunk, RiskLevel
from syssathi.knowledge.sources import SourceRegistry, get_source_registry
from syssathi.mcp_server.knowledge import explain_term, get_tool_recommendations, search_sources
from syssathi.skills.base import LessonCard
from syssathi.skills.errors import ErrorExplainerSkill
from syssathi.skills.explain import ExplainSkill
from syssathi.skills.howto import HowToSkill
from syssathi.skills.toolfinder import ToolFinderSkill


class TestSourceRegistry:
    def test_sources_yaml_loads(self) -> None:
        registry = get_source_registry()
        assert "fmhy" in registry.sources
        assert "wikipedia" in registry.sources
        assert "ms_learn" in registry.sources
        assert "eff_ssd" in registry.sources

    def test_source_licenses_verified(self) -> None:
        registry = get_source_registry()
        verifications = registry.verify_all_licenses()
        assert verifications["fmhy"] is True  # CC0-1.0
        assert verifications["wikipedia"] is True  # CC-BY-SA-4.0
        assert verifications["ms_learn"] is True  # Open-Documentation
        assert verifications["eff_ssd"] is True  # CC-BY-3.0

    def test_get_unknown_source(self) -> None:
        registry = get_source_registry()
        assert registry.get("unknown_source") is None


class TestContextLabeling:
    def test_safe_photo_tool_labeling(self) -> None:
        chunk = KnowledgeChunk(
            chunk_id="test-gimp",
            source_id="fmhy",
            category="photo_editing",
            title="GIMP",
            url="https://www.gimp.org",
            description="Open source image editor",
        )
        labeled = apply_context_labels(chunk)
        assert labeled.risk_level == RiskLevel.SAFE
        assert len(labeled.context_notes) > 0
        rec = build_tool_recommendation(labeled)
        assert rec.name == "GIMP"
        assert len(rec.download_safety_tips) > 0

    def test_p2p_torrent_context_labeling_educate_dont_block(self) -> None:
        chunk = KnowledgeChunk(
            chunk_id="test-qbittorrent",
            source_id="fmhy",
            category="p2p_torrent",
            title="qBittorrent",
            url="https://www.qbittorrent.org",
            description="Free open source torrent client",
        )
        labeled = apply_context_labels(chunk)
        # Not blocked, but labeled with caution and neutral legal note
        assert labeled.risk_level == RiskLevel.CAUTION
        assert "Legal Notice" in labeled.legal_note
        assert any("IP address" in note for note in labeled.context_notes)

        rec = build_tool_recommendation(labeled)
        assert rec.risk_level == RiskLevel.CAUTION
        assert len(rec.download_safety_tips) > 0

    def test_vpn_privacy_labeling(self) -> None:
        chunk = KnowledgeChunk(
            chunk_id="test-vpn",
            source_id="fmhy",
            category="privacy_security",
            title="Proton VPN",
            url="https://protonvpn.com",
            description="Free unlimited bandwidth VPN",
        )
        labeled = apply_context_labels(chunk)
        assert any("encrypts" in note.lower() for note in labeled.context_notes)


class TestKnowledgeIndex:
    @pytest.fixture
    def mem_index(self) -> KnowledgeIndex:
        return KnowledgeIndex(":memory:")

    def test_index_integrity_and_seeding(self, mem_index: KnowledgeIndex) -> None:
        assert mem_index.verify_index_integrity() is True

    def test_search_sources_bm25(self, mem_index: KnowledgeIndex) -> None:
        results = mem_index.search_sources("photo editing")
        assert len(results) > 0
        titles = [r.title for r in results]
        assert any("Photopea" in t or "GIMP" in t or "Paint.NET" in t for t in titles)

    def test_search_sources_empty_query(self, mem_index: KnowledgeIndex) -> None:
        results = mem_index.search_sources("   ")
        assert results == []

    def test_get_tool_recommendations(self, mem_index: KnowledgeIndex) -> None:
        recs = mem_index.get_tool_recommendations("video editing", os_name="windows")
        assert len(recs) > 0
        names = [r.name for r in recs]
        assert any("DaVinci Resolve" in n or "HandBrake" in n for n in names)
        assert all(r.source == "fmhy" for r in recs)

    def test_explain_term_concept(self, mem_index: KnowledgeIndex) -> None:
        ram_info = mem_index.explain_term("RAM")
        assert ram_info["found"] is True
        assert "Random Access Memory" in ram_info["title"]
        assert ram_info["citation"]["url"].startswith("http")

    def test_explain_term_unknown(self, mem_index: KnowledgeIndex) -> None:
        res = mem_index.explain_term("non_existent_term_xyz_123")
        assert res["found"] is False


class TestMCPKnowledgeTools:
    def test_search_sources_tool(self) -> None:
        res = search_sources("wifi password", k=3)
        assert res["count"] > 0
        assert "results" in res
        first = res["results"][0]
        assert "title" in first
        assert "url" in first

    def test_get_tool_recommendations_tool(self) -> None:
        res = get_tool_recommendations("photo editing")
        assert res["count"] > 0
        assert "recommendations" in res
        first = res["recommendations"][0]
        assert "download_safety_tips" in first

    def test_explain_term_tool(self) -> None:
        res = explain_term("VPN")
        assert res["found"] is True
        assert "citation" in res


class TestCitationGrounding:
    def test_extract_urls_from_text(self) -> None:
        text = "Visit https://www.photopea.com and https://gimp.org/downloads for free tools."
        urls = extract_urls_from_text(text)
        assert "https://www.photopea.com" in urls
        assert "https://gimp.org/downloads" in urls

    def test_collect_allowed_urls_nested(self) -> None:
        data = {
            "recommendations": [
                {"name": "GIMP", "url": "https://www.gimp.org"},
                {"name": "VLC", "url": "https://videolan.org/vlc/"},
            ],
            "citation": {"url": "https://en.wikipedia.org/wiki/RAM"},
        }
        allowed = collect_allowed_urls(data)
        assert "https://www.gimp.org" in allowed
        assert "https://videolan.org/vlc" in allowed
        assert "https://en.wikipedia.org/wiki/RAM" in allowed

    def test_verify_reply_citations_grounded(self) -> None:
        tool_data = {
            "recommendations": [{"name": "Photopea", "url": "https://www.photopea.com"}]
        }
        reply = "Aap Photopea use kar sakte hain jo https://www.photopea.com par uplabdh hai."
        is_valid, ungrounded = verify_reply_citations(reply, tool_data)
        assert is_valid is True
        assert ungrounded == []

    def test_verify_reply_citations_hallucinated(self) -> None:
        tool_data = {
            "recommendations": [{"name": "Photopea", "url": "https://www.photopea.com"}]
        }
        reply = "Download karein https://malicious-crack-site.com/photopea se."
        is_valid, ungrounded = verify_reply_citations(reply, tool_data)
        assert is_valid is False
        assert "https://malicious-crack-site.com/photopea" in ungrounded

    def test_format_template_reply_knowledge(self) -> None:
        tool_data = {
            "recommendations": [
                {
                    "name": "7-Zip",
                    "url": "https://www.7-zip.org",
                    "why_recommended": "Open source archiver",
                    "download_safety_tips": ["Download from official site."],
                }
            ]
        }
        reply = format_template_reply(tool_data)
        assert "7-Zip" in reply
        assert "https://www.7-zip.org" in reply


class TestIngestionAndManifest:
    def test_parse_markdown_source(self) -> None:
        sample_md = """
# Photo Editing Tools
* [Photopea](https://www.photopea.com) - Online photo editor ⭐ recommended
* [qBittorrent](https://www.qbittorrent.org) - Open source torrent client
        """
        chunks = parse_markdown_source(sample_md, source_id="fmhy")
        assert len(chunks) == 2
        assert chunks[0].title == "Photopea"
        assert chunks[0].risk_level == RiskLevel.SAFE
        assert "⭐ recommended" in chunks[0].tags
        assert chunks[1].title == "qBittorrent"
        assert chunks[1].risk_level == RiskLevel.CAUTION

    def test_compute_index_manifest(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            f.write(b"mock database contents for manifest test")
            temp_path = Path(f.name)

        try:
            manifest = compute_index_manifest(temp_path)
            assert manifest["file_name"] == temp_path.name
            assert manifest["file_size_bytes"] > 0
            assert len(manifest["sha256"]) == 64
            assert manifest["signed"] is True
        finally:
            if temp_path.exists():
                temp_path.unlink()


class TestSkillsLessonCards:
    def test_explain_skill_lesson_card(self) -> None:
        skill = ExplainSkill()
        assert "explain_term" in skill.get_tools()
        data = {
            "title": "RAM (Random Access Memory)",
            "summary": "Desk surface analogy for active memory.",
            "context_notes": ["Keep unused tabs closed."],
            "citation": {"url": "https://en.wikipedia.org/wiki/RAM"},
        }
        card = skill.build_lesson_card(data)
        assert card is not None
        assert isinstance(card, LessonCard)
        assert "RAM" in card.title

    def test_toolfinder_skill_lesson_card(self) -> None:
        skill = ToolFinderSkill()
        assert "get_tool_recommendations" in skill.get_tools()
        data = {
            "recommendations": [
                {
                    "name": "GIMP",
                    "why_recommended": "Open source photo editor",
                    "url": "https://www.gimp.org",
                    "download_safety_tips": ["Download from official site."],
                }
            ]
        }
        card = skill.build_lesson_card(data)
        assert card is not None
        assert "GIMP" in card.title
        assert "official site" in card.actionable_tip

    def test_howto_skill_lesson_card(self) -> None:
        skill = HowToSkill()
        data = {
            "results": [
                {
                    "title": "How to Change Wi-Fi Password",
                    "summary": "Router settings guide",
                    "content": "1. Go to 192.168.1.1 2. Log in 3. Change password",
                    "url": "https://learn.microsoft.com",
                }
            ]
        }
        card = skill.build_lesson_card(data)
        assert card is not None
        assert "Wi-Fi" in card.title

    def test_error_explainer_skill_lesson_card(self) -> None:
        skill = ErrorExplainerSkill()
        data = {
            "title": "Error 0x80070005: Access Denied",
            "summary": "Permissions issue",
            "detailed_explanation": "Run as administrator or check folder ACLs.",
            "citation": {"url": "https://learn.microsoft.com"},
        }
        card = skill.build_lesson_card(data)
        assert card is not None
        assert "0x80070005" in card.title

