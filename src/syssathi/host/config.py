"""Central configuration — loads .env and re-exports policy values."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

from syssathi.mcp_server.policy import get_thresholds, is_protected  # noqa: F401

# Load .env from the project root
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(_PROJECT_ROOT / ".env")

# ---------------------------------------------------------------------------
# LLM backend selection
# ---------------------------------------------------------------------------
# SYSSATHI_LLM_BACKEND: "evon_remote" | "openai_compatible" | "mock"
LLM_BACKEND: str = os.environ.get("SYSSATHI_LLM_BACKEND", "mock")

# Evon endpoint (section 4)
EVON_BASE_URL: str = os.environ.get(
    "EVON_BASE_URL",
    "https://6aec3eed62710132ca850c91.endpoints.huggingface.cloud/v1",
)
HF_TOKEN: str = os.environ.get("HF_TOKEN", "")
EVON_MODEL: str = os.environ.get("EVON_MODEL", "")

# openai_compatible fallback endpoint
OPENAI_COMPAT_BASE_URL: str = os.environ.get("OPENAI_COMPAT_BASE_URL", "")
OPENAI_COMPAT_API_KEY: str = os.environ.get("OPENAI_COMPAT_API_KEY", "")
OPENAI_COMPAT_MODEL: str = os.environ.get("OPENAI_COMPAT_MODEL", "")

# Reply style
REPLY_STYLE: str = os.environ.get("REPLY_STYLE", "latin")

# Fast path flag
FORCE_FAST_PATH: bool = os.environ.get("FORCE_FAST_PATH", "true").lower() in (
    "true",
    "1",
    "yes",
)

# Approval token (host generates per run, passes to MCP server subprocess)
APPROVAL_TOKEN: str = os.environ.get("SYSSATHI_APPROVAL_TOKEN", "")

# ---------------------------------------------------------------------------
# Gnani speech APIs (Phase 3)
# ---------------------------------------------------------------------------
GNANI_API_KEY: str = os.environ.get("GNANI_API_KEY", "")
PRISMA_MODE: str = os.environ.get("PRISMA_MODE", "Code-mix")
TIMBRE_VOICE: str = os.environ.get("TIMBRE_VOICE", "Shivani")
KEYTERMS_LIST: list[str] = [
    "Chrome",
    "Teams",
    "Spotify",
    "OneDrive",
    "Edge",
    "Zoom",
]

# ---------------------------------------------------------------------------
# Router keyword list (section 8, Addendum A4)
# ---------------------------------------------------------------------------
SLOWNESS_KEYWORDS: list[str] = [
    "slow",
    "hang",
    "lag",
    "laggy",
    "dheema",
    "dhima",
    "atak",
    "freeze",
    "slow chal",
]

# ---------------------------------------------------------------------------
# Logs directory
# ---------------------------------------------------------------------------
LOGS_DIR: Path = _PROJECT_ROOT / "logs"
