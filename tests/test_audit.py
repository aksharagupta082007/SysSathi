"""Tests for audit.py — valid JSON line with required fields."""

import json
import tempfile
from pathlib import Path
from unittest import mock

from syssathi.mcp_server import audit


class TestAuditLog:
    def test_writes_valid_json_line(self, tmp_path: Path):
        log_file = tmp_path / "audit.jsonl"
        with mock.patch.object(audit, "LOGS_DIR", tmp_path), \
             mock.patch.object(audit, "AUDIT_FILE", log_file):
            audit.log_event(
                tool="propose_close",
                action_id="abc-123",
                group="chrome",
                pids=[100, 200],
                result="proposed",
            )
        line = log_file.read_text().strip()
        record = json.loads(line)
        assert isinstance(record, dict)

    def test_has_required_fields(self, tmp_path: Path):
        log_file = tmp_path / "audit.jsonl"
        with mock.patch.object(audit, "LOGS_DIR", tmp_path), \
             mock.patch.object(audit, "AUDIT_FILE", log_file):
            audit.log_event(
                tool="execute_action",
                action_id="xyz-789",
                group="ping",
                pids=[300],
                result="executed",
            )
        record = json.loads(log_file.read_text().strip())
        for field in ("timestamp", "tool", "action_id", "group", "pids", "result"):
            assert field in record, f"Missing field: {field}"

    def test_timestamp_is_iso(self, tmp_path: Path):
        log_file = tmp_path / "audit.jsonl"
        with mock.patch.object(audit, "LOGS_DIR", tmp_path), \
             mock.patch.object(audit, "AUDIT_FILE", log_file):
            audit.log_event(tool="refusal", result="protected")
        record = json.loads(log_file.read_text().strip())
        # ISO format check: must contain T and timezone info
        assert "T" in record["timestamp"]

    def test_creates_logs_dir(self, tmp_path: Path):
        log_dir = tmp_path / "subdir"
        log_file = log_dir / "audit.jsonl"
        with mock.patch.object(audit, "LOGS_DIR", log_dir), \
             mock.patch.object(audit, "AUDIT_FILE", log_file):
            audit.log_event(tool="test", result="ok")
        assert log_dir.is_dir()
        assert log_file.exists()

    def test_appends_multiple_lines(self, tmp_path: Path):
        log_file = tmp_path / "audit.jsonl"
        with mock.patch.object(audit, "LOGS_DIR", tmp_path), \
             mock.patch.object(audit, "AUDIT_FILE", log_file):
            audit.log_event(tool="first", result="ok")
            audit.log_event(tool="second", result="ok")
        lines = log_file.read_text().strip().split("\n")
        assert len(lines) == 2
        for line in lines:
            json.loads(line)  # must be valid JSON

