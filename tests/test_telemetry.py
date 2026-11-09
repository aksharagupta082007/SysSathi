"""Tests for local opt-in telemetry and metrics dashboard (Phase F §8)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

from syssathi.core.telemetry import (
    compute_summary_stats,
    get_telemetry_file_path,
    is_telemetry_enabled,
    record_turn_telemetry,
    render_dashboard_text,
)


class TestTelemetryDisabledByDefault:
    def test_telemetry_disabled_by_default(self):
        # Default setting should be disabled
        assert not is_telemetry_enabled()

    def test_record_does_nothing_when_disabled(self, tmp_path: Path):
        log_file = tmp_path / "timings.jsonl"
        with mock.patch("syssathi.core.telemetry.is_telemetry_enabled", return_value=False):
            record_turn_telemetry(
                session_id="test-session-12345",
                route="fast",
                total_ms=450.0,
                filler_ms=120.0,
                first_sentence_ms=380.0,
                file_path=log_file,
            )
        assert not log_file.exists()


class TestTelemetryRecordingAndStats:
    def test_record_turn_when_enabled(self, tmp_path: Path):
        log_file = tmp_path / "timings.jsonl"
        with mock.patch("syssathi.core.telemetry.is_telemetry_enabled", return_value=True):
            record_turn_telemetry(
                session_id="abcdef123456",
                route="diagnose",
                total_ms=1200.0,
                tool_called="run_diagnosis",
                filler_ms=250.0,
                first_sentence_ms=850.0,
                language="hi",
                grounding_status="grounded",
                file_path=log_file,
            )

        assert log_file.exists()
        line = log_file.read_text(encoding="utf-8").strip()
        record = json.loads(line)

        assert record["session_id"] == "abcdef12"  # truncated for anonymity
        assert record["route"] == "diagnose"
        assert record["tool_called"] == "run_diagnosis"
        assert record["total_ms"] == 1200.0
        assert record["filler_ms"] == 250.0
        assert record["first_sentence_ms"] == 850.0
        assert record["grounding_status"] == "grounded"

    def test_compute_stats_empty_or_missing(self, tmp_path: Path):
        missing_file = tmp_path / "nonexistent.jsonl"
        res = compute_summary_stats(file_path=missing_file)
        assert res["total_turns"] == 0

        empty_file = tmp_path / "empty.jsonl"
        empty_file.write_text("")
        res_empty = compute_summary_stats(file_path=empty_file)
        assert res_empty["total_turns"] == 0

    def test_compute_stats_percentiles_and_compliance(self, tmp_path: Path):
        log_file = tmp_path / "timings.jsonl"
        with mock.patch("syssathi.core.telemetry.is_telemetry_enabled", return_value=True):
            # Record 10 turns with varied latencies
            for i in range(1, 11):
                record_turn_telemetry(
                    session_id=f"sess-{i}",
                    route="fast",
                    total_ms=float(i * 200),  # 200 to 2000 ms
                    tool_called="get_top_processes" if i % 2 == 0 else "search_sources",
                    filler_ms=float(i * 100),  # 100 to 1000 ms (< 1500ms target)
                    first_sentence_ms=float(i * 300),  # 300 to 3000 ms (< 4000ms target)
                    grounding_status="grounded",
                    file_path=log_file,
                )

        stats = compute_summary_stats(file_path=log_file)
        assert stats["total_turns"] == 10
        assert stats["grounding_pass_rate_pct"] == 100.0
        assert stats["targets"]["filler_under_1_5s"] is True
        assert stats["targets"]["sentence_under_4s"] is True
        assert stats["targets"]["grounding_100_pct"] is True
        assert stats["tools_breakdown"]["get_top_processes"] == 5
        assert stats["tools_breakdown"]["search_sources"] == 5

    def test_render_dashboard_text(self, tmp_path: Path):
        log_file = tmp_path / "timings.jsonl"
        with mock.patch("syssathi.core.telemetry.is_telemetry_enabled", return_value=True):
            record_turn_telemetry(
                session_id="s1",
                route="diagnose",
                total_ms=1500.0,
                tool_called="run_diagnosis",
                filler_ms=300.0,
                first_sentence_ms=1100.0,
                grounding_status="grounded",
                file_path=log_file,
            )

        stats = compute_summary_stats(file_path=log_file)
        dashboard = render_dashboard_text(stats)

        assert "SysSathi Local Telemetry Dashboard" in dashboard
        assert "Total Recorded Turns:       1" in dashboard
        assert "Grounded Claim Rate:        100.0%" in dashboard
        assert "PASS" in dashboard

