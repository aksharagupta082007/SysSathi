"""Tests for host/timing.py — one JSON line per request."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from syssathi.host.timing import Timer


@pytest.fixture
def tmp_logs(tmp_path: Path) -> Path:
    """Return a temporary logs directory."""
    logs = tmp_path / "logs"
    logs.mkdir()
    return logs


class TestTimingLine:
    """Timer records fields and flushes one JSON line."""

    def test_flush_creates_file(self, tmp_logs: Path) -> None:
        t = Timer(logs_dir=tmp_logs)
        t.set("route", "fast")
        t.flush()
        path = tmp_logs / "timings.jsonl"
        assert path.exists()

    def test_flush_writes_valid_json(self, tmp_logs: Path) -> None:
        t = Timer(logs_dir=tmp_logs)
        t.set("route", "fast")
        record = t.flush()
        path = tmp_logs / "timings.jsonl"
        line = path.read_text(encoding="utf-8").strip()
        parsed = json.loads(line)
        assert parsed == record

    def test_total_ms_present(self, tmp_logs: Path) -> None:
        t = Timer(logs_dir=tmp_logs)
        t.set("route", "evon")
        record = t.flush()
        assert "total_ms" in record
        assert isinstance(record["total_ms"], float)
        assert record["total_ms"] >= 0

    def test_mark_records_ms(self, tmp_logs: Path) -> None:
        t = Timer(logs_dir=tmp_logs)
        start = time.perf_counter()
        time.sleep(0.01)
        t.mark("llm1_ms", start)
        record = t.flush()
        assert "llm1_ms" in record
        assert record["llm1_ms"] >= 5  # at least 5ms from 10ms sleep

    def test_route_field(self, tmp_logs: Path) -> None:
        t = Timer(logs_dir=tmp_logs)
        t.set("route", "fast")
        record = t.flush()
        assert record["route"] == "fast"

    def test_multiple_flushes_append(self, tmp_logs: Path) -> None:
        t1 = Timer(logs_dir=tmp_logs)
        t1.set("route", "fast")
        t1.flush()

        t2 = Timer(logs_dir=tmp_logs)
        t2.set("route", "evon")
        t2.flush()

        path = tmp_logs / "timings.jsonl"
        lines = path.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 2
        assert json.loads(lines[0])["route"] == "fast"
        assert json.loads(lines[1])["route"] == "evon"

    def test_all_expected_fields(self, tmp_logs: Path) -> None:
        """Verify the fields from BRIEF section 8."""
        t = Timer(logs_dir=tmp_logs)
        t.set("route", "fast")
        start = time.perf_counter()
        t.mark("llm1_ms", start)
        t.mark("tool_ms", start)
        t.mark("llm2_ms", start)
        record = t.flush()
        for field in ("route", "llm1_ms", "tool_ms", "llm2_ms", "total_ms"):
            assert field in record, f"Missing field: {field}"


class TestTimerAutoDir:
    """Timer creates logs dir if it doesn't exist."""

    def test_creates_missing_dir(self, tmp_path: Path) -> None:
        logs = tmp_path / "nonexistent" / "logs"
        t = Timer(logs_dir=logs)
        t.set("route", "test")
        t.flush()
        assert (logs / "timings.jsonl").exists()

