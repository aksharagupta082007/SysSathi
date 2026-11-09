"""Context labeling pipeline (Decision 3: Educate, don't block §6.3)."""

from __future__ import annotations

from typing import Any
from syssathi.knowledge.models import KnowledgeChunk, RiskLevel, ToolRecommendation

# Universal download safety advice
STANDARD_DOWNLOAD_SAFETY = [
    "Download only from the official project homepage or verified GitHub release page.",
    "Beware of deceptive third-party banner ads with fake 'Download' or 'Start' buttons.",
    "Scan downloaded installers with Windows Defender or VirusTotal before running.",
]

SYSTEM_TWEAK_SAFETY = [
    "Create a Windows System Restore point before applying registry tweaks or debloaters.",
    "Avoid running automated cleaner scripts with administrator privileges unless you review their actions.",
]

P2P_SAFETY_NOTES = [
    "Torrenting publicly broadcasts your IP address to swarm peers. Bind your torrent client to a trusted VPN interface if privacy is required.",
    "Never run downloaded .exe, .bat, or .vbs files from unknown swarms without scanning and checking hashes.",
    "Use open-source, ad-free clients (like qBittorrent) rather than clients with bundled promotional adware.",
]

P2P_LEGAL_NOTE = (
    "Legal Notice: The legality of downloading or streaming copyrighted material depends on local laws "
    "and copyright owner permissions. SysSathi provides technical and educational information only."
)

VPN_PRIVACY_NOTES = [
    "A VPN encrypts the tunnel between your PC and the VPN server; it does not protect against downloaded malware or phishing sites.",
    "Avoid questionable free VPNs that monetize by selling user browsing history. Choose audited no-logs providers.",
]


def apply_context_labels(chunk: KnowledgeChunk) -> KnowledgeChunk:
    """Analyze a knowledge chunk and apply safety, context, and legal tags.

    Adheres strictly to Decision 3 (Educate, don't block):
    No entry is ever removed or hidden. Instead, rich educational context,
    risk levels, and safety guidance are attached.
    """
    category_lower = chunk.category.lower()
    title_lower = chunk.title.lower()
    desc_lower = chunk.description.lower()
    text = f"{category_lower} {title_lower} {desc_lower}"

    # P2P / Torrents / Streaming / Unofficial downloads
    if any(k in text for k in ("torrent", "p2p", "piracy", "streaming", "warez", "cracked", "bypass")):
        chunk.risk_level = RiskLevel.CAUTION
        chunk.legal_note = P2P_LEGAL_NOTE
        for note in P2P_SAFETY_NOTES:
            if note not in chunk.context_notes:
                chunk.context_notes.append(note)

    # Privacy / VPNs / DNS / Encryption
    elif any(k in text for k in ("vpn", "proxy", "dns", "privacy", "tor", "encryption")):
        if "free vpn" in text and "proton" not in text and "mullvad" not in text:
            chunk.risk_level = RiskLevel.CAUTION
        for note in VPN_PRIVACY_NOTES:
            if note not in chunk.context_notes:
                chunk.context_notes.append(note)

    # System cleaners / Registry / Debloaters
    elif any(k in text for k in ("debloat", "registry", "cleaner", "tweak", "optimizer", "driver updater")):
        chunk.risk_level = RiskLevel.CAUTION
        for note in SYSTEM_TWEAK_SAFETY:
            if note not in chunk.context_notes:
                chunk.context_notes.append(note)

    # General software & utilities
    else:
        if not chunk.context_notes:
            chunk.context_notes.extend(STANDARD_DOWNLOAD_SAFETY[:2])

    return chunk


def build_tool_recommendation(chunk: KnowledgeChunk) -> ToolRecommendation:
    """Transform a labeled KnowledgeChunk into a structured ToolRecommendation."""
    tips = list(STANDARD_DOWNLOAD_SAFETY)
    if chunk.risk_level == RiskLevel.CAUTION:
        tips = list(P2P_SAFETY_NOTES if "torrent" in chunk.category.lower() else SYSTEM_TWEAK_SAFETY)

    return ToolRecommendation(
        name=chunk.title,
        url=chunk.url,
        category=chunk.category,
        why_recommended=chunk.description,
        risk_level=chunk.risk_level,
        context_notes=list(chunk.context_notes),
        legal_note=chunk.legal_note,
        tags=list(chunk.tags),
        download_safety_tips=tips,
        source=chunk.source_id,
    )

