"""Audit log — one JSON line per event to logs/audit.jsonl."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from syssathi.core.privacy import scrub_secrets


def _get_logs_dir() -> Path:
    env_dir = os.environ.get("SYSSATHI_LOG_DIR")
    if env_dir:
        return Path(env_dir)
    # Check if project root exists
    proj_root = Path(__file__).resolve().parents[3]
    if (proj_root / "pyproject.toml").exists():
        return proj_root / "logs"
    import platformdirs
    return Path(platformdirs.user_log_dir("syssathi"))


LOGS_DIR = _get_logs_dir()
AUDIT_FILE = LOGS_DIR / "audit.jsonl"
MAX_LOG_SIZE = 5 * 1024 * 1024  # 5 MB


def _rotate_audit_file(audit_path: Path) -> None:
    """Rotate audit.jsonl to audit.1.jsonl if size >= MAX_LOG_SIZE."""
    if not audit_path.exists():
        return
    try:
        if audit_path.stat().st_size >= MAX_LOG_SIZE:
            backup_path = audit_path.with_name("audit.1.jsonl")
            if backup_path.exists():
                backup_path.unlink()
            audit_path.rename(backup_path)
    except OSError:
        pass


def log_event(
    *,
    tool: str,
    action_id: str | None = None,
    group: str | None = None,
    pids: list[int] | None = None,
    result: str,
    session_id: str | None = None,
    actor: str | None = None,
) -> None:
    """Append one JSON line to the audit log with size-based rotation."""
    target_dir = LOGS_DIR
    target_file = AUDIT_FILE
    target_dir.mkdir(parents=True, exist_ok=True)
    _rotate_audit_file(target_file)

    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "tool": tool,
        "action_id": action_id,
        "group": group,
        "pids": pids or [],
        "result": result,
        "session_id": session_id,
        "actor": actor,
    }
    raw_line = json.dumps(record, ensure_ascii=False)
    clean_line = scrub_secrets(raw_line)
    with open(target_file, "a", encoding="utf-8") as f:
        f.write(clean_line + "\n")
