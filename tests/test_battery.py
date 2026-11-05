"""Tests for battery.py — fake PS JSON, no-battery, no-health."""

from types import SimpleNamespace

from syssathi.mcp_server.battery import parse_battery


def _fake_battery(percent: float = 75.0, plugged: bool = False):
    return SimpleNamespace(percent=percent, power_plugged=plugged)


class TestParseBattery:
    def test_no_battery(self):
        result = parse_battery(None, None, None)
        assert result == {"has_battery": False}

    def test_basic_battery_no_health(self):
        result = parse_battery(_fake_battery(80.0, True), None, None)
        assert result["has_battery"] is True
        assert result["charge_pct"] == 80.0
        assert result["plugged"] is True
        assert result["health_available"] is False

    def test_battery_with_health(self):
        static_json = '{"DesignedCapacity": 50000}'
        full_json = '{"FullChargedCapacity": 45000}'
        result = parse_battery(_fake_battery(65.0, False), static_json, full_json)
        assert result["has_battery"] is True
        assert result["charge_pct"] == 65.0
        assert result["plugged"] is False
        assert result["designed_capacity_mwh"] == 50000
        assert result["full_charge_capacity_mwh"] == 45000
        assert result["health_pct"] == 90.0  # 45000/50000 * 100

    def test_battery_ps_list_format(self):
        """PowerShell sometimes returns a list."""
        static_json = '[{"DesignedCapacity": 40000}]'
        full_json = '[{"FullChargedCapacity": 36000}]'
        result = parse_battery(_fake_battery(), static_json, full_json)
        assert result["designed_capacity_mwh"] == 40000
        assert result["health_pct"] == 90.0

    def test_battery_ps_empty_list(self):
        result = parse_battery(_fake_battery(), "[]", "[]")
        assert result["health_available"] is False

    def test_battery_invalid_json(self):
        result = parse_battery(_fake_battery(), "not json", "also bad")
        assert result["health_available"] is False

    def test_battery_ps_missing_key(self):
        result = parse_battery(_fake_battery(), '{"Other": 1}', '{"Other": 2}')
        assert result["health_available"] is False

    def test_plugged_default_false(self):
        bat = SimpleNamespace(percent=50.0, power_plugged=None)
        result = parse_battery(bat, None, None)
        assert result["plugged"] is False

