"""Tests for process grouping — pure logic on fake data."""

from syssathi.mcp_server.processes import group_process_list


def _make_entry(name: str, rss_mb: float, cpu_pct: float) -> dict:
    return {"name": name, "rss_bytes": int(rss_mb * 1024 * 1024), "cpu_pct": cpu_pct}


class TestGroupProcessList:
    def test_basic_grouping(self):
        entries = [
            _make_entry("chrome.exe", 500, 10.0),
            _make_entry("Chrome.exe", 300, 5.0),
        ]
        groups = group_process_list(entries, cpu_count=4)
        assert len(groups) == 1
        assert groups[0]["name"] == "chrome"
        assert groups[0]["procs"] == 2
        assert groups[0]["ram_mb"] == 800.0
        assert groups[0]["cpu_pct"] == 3.8  # (10+5)/4 = 3.75 -> 3.8

    def test_case_insensitive(self):
        entries = [
            _make_entry("NOTEPAD.EXE", 100, 2.0),
            _make_entry("notepad.exe", 100, 2.0),
            _make_entry("Notepad", 100, 2.0),
        ]
        groups = group_process_list(entries, cpu_count=1)
        assert len(groups) == 1
        assert groups[0]["name"] == "notepad"
        assert groups[0]["procs"] == 3

    def test_exe_removed(self):
        entries = [_make_entry("code.exe", 200, 1.0)]
        groups = group_process_list(entries, cpu_count=1)
        assert groups[0]["name"] == "code"

    def test_summed_ram(self):
        entries = [
            _make_entry("app", 100, 0),
            _make_entry("app", 200, 0),
            _make_entry("app", 300, 0),
        ]
        groups = group_process_list(entries, cpu_count=1)
        assert groups[0]["ram_mb"] == 600.0

    def test_cpu_divided_by_cpu_count(self):
        entries = [_make_entry("app", 100, 400.0)]
        # 8-core: 400/8 = 50
        groups = group_process_list(entries, cpu_count=8)
        assert groups[0]["cpu_pct"] == 50.0

    def test_top_5_cut(self):
        entries = [_make_entry(f"app{i}", (10 - i) * 100, 1.0) for i in range(8)]
        groups = group_process_list(entries, cpu_count=1)
        assert len(groups) == 5
        # Sorted by RAM descending
        assert groups[0]["ram_mb"] >= groups[1]["ram_mb"]

    def test_sanitize_applied(self):
        # Control characters in name should be stripped
        entries = [_make_entry("chr\x00ome.exe", 100, 1.0)]
        groups = group_process_list(entries, cpu_count=1)
        assert groups[0]["name"] == "chrome"

    def test_path_in_name_uses_basename(self):
        entries = [_make_entry(r"C:\Program Files\app.exe", 100, 1.0)]
        groups = group_process_list(entries, cpu_count=1)
        assert groups[0]["name"] == "app"

    def test_empty_list(self):
        groups = group_process_list([], cpu_count=4)
        assert groups == []


class TestAccessDeniedSkipped:
    """Verify that group_process_list handles only valid entries.

    AccessDenied/NoSuchProcess are handled at the sampling layer.
    We verify that the grouping function works with the filtered list.
    """

    def test_works_with_filtered_list(self):
        # Simulate: process iter already filtered out bad entries
        entries = [_make_entry("chrome", 200, 5.0)]
        groups = group_process_list(entries, cpu_count=1)
        assert len(groups) == 1

