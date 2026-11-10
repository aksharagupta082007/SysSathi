"""Tests for Phase E: CLI subcommands, privacy path redaction, and PWA assets."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from syssathi.core.privacy import redact_paths_and_users, sanitize_payload_for_telemetry_or_api, scrub_secrets
from syssathi.host.cli import cmd_ask, cmd_diagnose, cmd_index, cmd_telemetry
from syssathi.web.app import app


class TestPrivacyRedaction:
    def test_redact_windows_user_path(self) -> None:
        raw = r"File located at C:\Users\john_doe\Documents\secret.txt and C:\Users\admin\Desktop"
        clean = redact_paths_and_users(raw, username="john_doe")
        assert r"C:\Users\<user>\Documents\secret.txt" in clean
        assert r"C:\Users\<user>\Desktop" in clean
        assert "john_doe" not in clean

    def test_redact_unix_user_path(self) -> None:
        raw = "Logs at /home/developer/app.log and /Users/developer/Music"
        clean = redact_paths_and_users(raw, username="developer")
        assert "/home/<user>/app.log" in clean
        assert "/Users/<user>/Music" in clean
        assert "developer" not in clean

    def test_redact_standalone_username(self) -> None:
        raw = "User aayush is logged in."
        clean = redact_paths_and_users(raw, username="aayush")
        assert "<user>" in clean
        assert "aayush" not in clean

    def test_sanitize_payload_recursive(self) -> None:
        payload = {
            "path": r"C:\Users\testuser\report.pdf",
            "metadata": {
                "owner": "testuser",
                "nested_paths": [r"C:\Users\testuser\file1.txt", "safe_value"],
            },
        }
        sanitized = sanitize_payload_for_telemetry_or_api(payload, username="testuser")
        assert "<user>" in sanitized["path"]
        assert "testuser" not in sanitized["path"]
        assert sanitized["metadata"]["owner"] == "<user>"
        assert "<user>" in sanitized["metadata"]["nested_paths"][0]
        assert sanitized["metadata"]["nested_paths"][1] == "safe_value"

    def test_scrub_secrets_redaction(self) -> None:
        raw = (
            "Keys: gnani_1234567890abcdef and hf_secretkey987654321 "
            "and sk-proj01234567890 and Bearer auth_jwt_token_here"
        )
        scrubbed = scrub_secrets(raw)
        assert "gnani_1234567890abcdef" not in scrubbed
        assert "hf_secretkey987654321" not in scrubbed
        assert "sk-proj01234567890" not in scrubbed
        assert "auth_jwt_token_here" not in scrubbed
        assert "[REDACTED_GNANI_TOKEN]" in scrubbed
        assert "[REDACTED_HF_TOKEN]" in scrubbed
        assert "[REDACTED_API_KEY]" in scrubbed
        assert "[REDACTED_TOKEN]" in scrubbed


class TestCLISubcommands:
    @pytest.mark.asyncio
    async def test_cmd_diagnose_executes(self, capsys: pytest.CaptureFixture[str]) -> None:
        args = argparse.Namespace(command="diagnose")
        code = await cmd_diagnose(args)
        assert code == 0
        captured = capsys.readouterr().out
        assert "SYSTEM DIAGNOSTIC REPORT" in captured
        assert "CPU Average" in captured
        assert "RAM Usage" in captured

    @pytest.mark.asyncio
    async def test_cmd_ask_photo_edit(
        self, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("SYSSATHI_LLM_BACKEND", "mock")
        args = argparse.Namespace(
            command="ask",
            question="photo edit",
            lang="hi",
            script="latin",
        )
        code = await cmd_ask(args)
        assert code == 0
        captured = capsys.readouterr().out
        assert "SysSathi >" in captured
        assert "Sources & Recommendations" in captured or "Learn" in captured

    @pytest.mark.asyncio
    async def test_cmd_index_status(self, capsys: pytest.CaptureFixture[str]) -> None:
        args = argparse.Namespace(command="index", action="status")
        code = await cmd_index(args)
        assert code == 0
        captured = capsys.readouterr().out
        assert "Integrity Check:    PASS" in captured

    @pytest.mark.asyncio
    async def test_cmd_telemetry_executes(self, capsys: pytest.CaptureFixture[str]) -> None:
        args = argparse.Namespace(command="telemetry")
        code = await cmd_telemetry(args)
        assert code == 0
        captured = capsys.readouterr().out
        assert "Telemetry Dashboard" in captured


class TestPWAAssets:
    @pytest.fixture
    def client(self) -> TestClient:
        return TestClient(app)

    def test_manifest_json_endpoint(self, client: TestClient) -> None:
        resp = client.get("/static/manifest.json")
        assert resp.status_code == 200
        data = resp.json()
        assert data["short_name"] == "SysSathi"
        assert data["display"] == "standalone"
        assert len(data["icons"]) > 0

    def test_service_worker_asset(self, client: TestClient) -> None:
        resp = client.get("/static/sw.js")
        assert resp.status_code == 200
        assert "caches.open" in resp.text
        assert "syssathi-v1" in resp.text

    def test_icon_svg_asset(self, client: TestClient) -> None:
        resp = client.get("/static/icon.svg")
        assert resp.status_code == 200
        assert "<svg" in resp.text

    def test_index_html_has_pwa_and_cards(self, client: TestClient) -> None:
        resp = client.get("/")
        assert resp.status_code == 200
        html = resp.text
        assert 'rel="manifest" href="/static/manifest.json"' in html
        assert "serviceWorker.register" in html
        assert "lesson-card" in html or "appendLessonCard" in html
        assert "sources-container" in html or "appendSourcesCard" in html
        assert "Tap to Toggle" in html
        assert "Companion Settings" in html
