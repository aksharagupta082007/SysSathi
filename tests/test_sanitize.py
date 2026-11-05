"""Tests for sanitize.py — length, control characters, paths."""

from syssathi.mcp_server.sanitize import sanitize


class TestSanitizeLength:
    def test_short_string_unchanged(self):
        assert sanitize("chrome") == "chrome"

    def test_exactly_40_unchanged(self):
        s = "a" * 40
        assert sanitize(s) == s

    def test_truncates_at_41(self):
        s = "a" * 50
        assert len(sanitize(s)) == 40

    def test_long_string_truncated(self):
        s = "x" * 100
        assert sanitize(s) == "x" * 40


class TestSanitizeControlChars:
    def test_strips_null(self):
        assert sanitize("chr\x00ome") == "chrome"

    def test_strips_bell(self):
        assert sanitize("chr\x07ome") == "chrome"

    def test_strips_escape(self):
        assert sanitize("chr\x1bome") == "chrome"

    def test_strips_del(self):
        assert sanitize("chr\x7fome") == "chrome"

    def test_strips_c1_control(self):
        assert sanitize("chr\x8fome") == "chrome"

    def test_keeps_space(self):
        assert sanitize("Google Chrome") == "Google Chrome"

    def test_replaces_tab_with_space(self):
        assert sanitize("a\tb") == "a b"

    def test_replaces_newline_with_space(self):
        assert sanitize("a\nb") == "a b"


class TestSanitizePaths:
    def test_backslash_path(self):
        assert sanitize(r"C:\Program Files\Chrome\chrome.exe") == "chrome.exe"

    def test_forward_slash_path(self):
        assert sanitize("/usr/local/bin/python3") == "python3"

    def test_mixed_path(self):
        assert sanitize(r"C:\Users/someone\app.exe") == "app.exe"

    def test_no_path_unchanged(self):
        assert sanitize("notepad") == "notepad"

    def test_path_plus_truncation(self):
        name = "a" * 50 + ".exe"
        result = sanitize(r"C:\Programs\\" + name)
        assert len(result) == 40

