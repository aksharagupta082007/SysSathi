"""Central configuration — loads .env and re-exports policy values."""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv

from syssathi.mcp_server.policy import get_thresholds, is_protected  # noqa: F401

# Load .env from the project root
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(_PROJECT_ROOT / ".env")

