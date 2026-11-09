"""Tests for startup.py — parsing, no command lines, sanitize."""

from syssathi.mcp_server.startup import parse_startup_entries


class TestParseStartupEntries:
    def test_basic_registry(self):
        reg_entries = [("OneDrive", "HKCU_Run"), ("SecurityHealth", "HKLM_Run")]
        result = parse_startup_entries(reg_entries, [])
        assert len(result) == 2
        assert result[0]["name"] == "OneDrive"
        assert result[0]["source"] == "HKCU_Run"

    def test_folder_entries(self):
        result = parse_startup_entries([], ["Spotify.lnk", "Discord.lnk"])
        assert len(result) == 2
        assert result[0]["name"] == "Spotify"
        assert result[0]["source"] == "startup_folder"

    def test_combined(self):
        reg = [("OneDrive", "HKCU_Run")]
        folders = ["Spotify.lnk"]
        result = parse_startup_entries(reg, folders)
        assert len(result) == 2

    def test_no_command_lines(self):
        """Names must not contain paths or command lines."""
        reg = [("MyApp", "HKCU_Run")]
        result = parse_startup_entries(reg, [])
        for entry in result:
            assert "\\" not in entry["name"]
            assert "/" not in entry["name"]
            assert "source" in entry

    def test_sanitize_control_chars(self):
        reg = [("My\x00App", "HKCU_Run")]
        result = parse_startup_entries(reg, [])
        assert result[0]["name"] == "MyApp"

    def test_sanitize_long_name(self):
        long_name = "A" * 60
        reg = [(long_name, "HKCU_Run")]
        result = parse_startup_entries(reg, [])
        assert len(result[0]["name"]) == 40

    def test_empty(self):
        result = parse_startup_entries([], [])
        assert result == []

    def test_folder_strips_extension(self):
        result = parse_startup_entries([], ["MyApp.exe.lnk"])
        assert result[0]["name"] == "MyApp.exe"

    def test_parses_enabled_flag(self):
        reg = [("ActiveApp", "HKCU_Run", True), ("DisabledApp", "HKLM_Run", False)]
        folders = [("ActiveFolder.lnk", True), ("DisabledFolder.lnk", False)]
        result = parse_startup_entries(reg, folders)
        assert len(result) == 4
        assert result[0]["enabled"] is True
        assert result[1]["enabled"] is False
        assert result[2]["enabled"] is True
        assert result[3]["enabled"] is False

