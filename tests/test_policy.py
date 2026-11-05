"""Tests for policy.py — protected list, case, .exe, python substring, env override."""

import os
from unittest import mock

from syssathi.mcp_server.policy import get_thresholds, is_protected, normalize_process_name


class TestNormalizeProcessName:
    def test_lowercase(self):
        assert normalize_process_name("Chrome") == "chrome"

    def test_strip_exe(self):
        assert normalize_process_name("chrome.exe") == "chrome"

    def test_uppercase_exe(self):
        assert normalize_process_name("Chrome.EXE") == "chrome"

    def test_no_exe(self):
        assert normalize_process_name("svchost") == "svchost"


class TestIsProtected:
    def test_system(self):
        assert is_protected("System") is True

    def test_explorer(self):
        assert is_protected("explorer") is True

    def test_case_insensitive(self):
        assert is_protected("EXPLORER") is True
        assert is_protected("Explorer.exe") is True

    def test_with_exe(self):
        assert is_protected("csrss.exe") is True

    def test_python_substring(self):
        assert is_protected("python") is True
        assert is_protected("python3.11") is True
        assert is_protected("Python.exe") is True
        assert is_protected("pythonw") is True

    def test_svchost(self):
        assert is_protected("svchost") is True
        assert is_protected("svchost.exe") is True

    def test_msmpeng(self):
        assert is_protected("MsMpEng") is True
        assert is_protected("MsMpEng.exe") is True

    def test_chrome_not_protected(self):
        assert is_protected("chrome") is False
        assert is_protected("Chrome.exe") is False

    def test_notepad_not_protected(self):
        assert is_protected("notepad") is False

    def test_all_protected_names(self):
        protected = [
            "System", "System Idle Process", "Registry", "smss", "csrss",
            "wininit", "winlogon", "services", "lsass", "svchost",
            "explorer", "dwm", "fontdrvhost", "MsMpEng", "SecurityHealthService",
        ]
        for name in protected:
            assert is_protected(name) is True, f"{name} should be protected"


class TestThresholds:
    def test_defaults(self):
        th = get_thresholds()
        assert th["RAM_HIGH_PCT"] == 85.0
        assert th["DISK_LOW_PCT"] == 10.0
        assert th["STARTUP_HIGH_COUNT"] == 8
        assert th["CPU_HIGH_PCT"] == 80.0

    def test_env_override_ram(self):
        with mock.patch.dict(os.environ, {"SYSSATHI_RAM_HIGH_PCT": "90"}):
            th = get_thresholds()
            assert th["RAM_HIGH_PCT"] == 90.0

    def test_env_override_disk(self):
        with mock.patch.dict(os.environ, {"SYSSATHI_DISK_LOW_PCT": "15"}):
            th = get_thresholds()
            assert th["DISK_LOW_PCT"] == 15.0

    def test_env_override_startup(self):
        with mock.patch.dict(os.environ, {"SYSSATHI_STARTUP_HIGH_COUNT": "5"}):
            th = get_thresholds()
            assert th["STARTUP_HIGH_COUNT"] == 5

    def test_env_override_cpu(self):
        with mock.patch.dict(os.environ, {"SYSSATHI_CPU_HIGH_PCT": "70"}):
            th = get_thresholds()
            assert th["CPU_HIGH_PCT"] == 70.0

