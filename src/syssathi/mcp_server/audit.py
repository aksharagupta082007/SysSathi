"""Audit log — one JSON line per event to logs/audit.jsonl."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

LOGS_DIR = Path(__file__).resolve().parents[3] / "logs"
AUDIT_FILE = LOGS_DIR / "audit.jsonl"


def log_event(
    *,
    tool: str,
    action_id: str | None = None,
    group: str | None = None,
    pids: list[int] | None = None,
    result: str,
) -> None:
    """Append one JSON line to the audit log."""
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "tool": tool,
        "action_id": action_id,
        "group": group,
        "pids": pids or [],
        "result": result,
    }
    with open(AUDIT_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")

