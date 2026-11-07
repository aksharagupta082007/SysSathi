"""Tests for diagnose.py — threshold boundaries and schema validation."""

import os
from unittest import mock

import jsonschema
import pytest

from syssathi.mcp_server.diagnose import FINDINGS_SCHEMA, build_findings


@pytest.fixture(autouse=True)
def _standard_thresholds():
    with mock.patch.dict(
        os.environ,
        {
            "SYSSATHI_RAM_HIGH_PCT": "85.0",
            "SYSSATHI_DISK_LOW_PCT": "10.0",
            "SYSSATHI_STARTUP_HIGH_COUNT": "8",
            "SYSSATHI_CPU_HIGH_PCT": "80.0",
        },
    ):
        yield


def _default_kwargs(**overrides):
    base = {
        "cpu_samples": [50.0, 55.0, 60.0],
        "ram_used_pct": 50.0,
        "ram_total_gb": 16.0,
        "disk_free_pct": 50.0,
        "disk_mb_per_s": 5.0,
        "top_groups": [{"name": "chrome", "procs": 5, "ram_mb": 500.0, "cpu_pct": 10.0}],
        "startup_count": 5,
    }
    base.update(overrides)
    return base


class TestFindingsSchema:
    def test_output_validates(self):
        result = build_findings(**_default_kwargs())
        jsonschema.validate(result, FINDINGS_SCHEMA)

    def test_no_findings_when_healthy(self):
        result = build_findings(**_default_kwargs())
        assert result["findings"] == []


class TestRAMThreshold:
    """RAM_HIGH: above 85 means > 85 (85.0 is NOT high, 85.1 IS high)."""

    def test_85_not_high(self):
        result = build_findings(**_default_kwargs(ram_used_pct=85.0))
        codes = [f["code"] for f in result["findings"]]
        assert "RAM_HIGH" not in codes

    def test_85_1_is_high(self):
        result = build_findings(**_default_kwargs(ram_used_pct=85.1))
        codes = [f["code"] for f in result["findings"]]
        assert "RAM_HIGH" in codes


class TestDiskThreshold:
    """DISK_LOW: below 10 means < 10 (10.0 is NOT low, 9.9 IS low)."""

    def test_10_not_low(self):
        result = build_findings(**_default_kwargs(disk_free_pct=10.0))
        codes = [f["code"] for f in result["findings"]]
        assert "DISK_LOW" not in codes

    def test_9_9_is_low(self):
        result = build_findings(**_default_kwargs(disk_free_pct=9.9))
        codes = [f["code"] for f in result["findings"]]
        assert "DISK_LOW" in codes


class TestStartupThreshold:
    """STARTUP_HIGH: more than 8 means >= 9 (8 is NOT high, 9 IS high)."""

    def test_8_not_high(self):
        result = build_findings(**_default_kwargs(startup_count=8))
        codes = [f["code"] for f in result["findings"]]
        assert "STARTUP_HIGH" not in codes

    def test_9_is_high(self):
        result = build_findings(**_default_kwargs(startup_count=9))
        codes = [f["code"] for f in result["findings"]]
        assert "STARTUP_HIGH" in codes


class TestCPUThreshold:
    """CPU_HIGH: above 80 means > 80 (80.0 is NOT high, 80.1 IS high)."""

    def test_80_not_high(self):
        result = build_findings(**_default_kwargs(cpu_samples=[80.0, 80.0, 80.0]))
        codes = [f["code"] for f in result["findings"]]
        assert "CPU_HIGH" not in codes

    def test_80_1_is_high(self):
        result = build_findings(**_default_kwargs(cpu_samples=[80.1, 80.1, 80.1]))
        codes = [f["code"] for f in result["findings"]]
        assert "CPU_HIGH" in codes


class TestCPUComputedValues:
    def test_avg_and_peak(self):
        result = build_findings(**_default_kwargs(cpu_samples=[10.0, 20.0, 90.0]))
        assert result["cpu_avg_pct"] == 40.0
        assert result["cpu_peak_pct"] == 90.0

