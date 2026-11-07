"""Offline unit tests for FastAPI web app, security checks, and audio pipeline."""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from syssathi.web.app import app


class TestWebApp:
    @pytest.fixture(autouse=True)
    def _force_mock_backend(self, monkeypatch):
        monkeypatch.setenv("SYSSATHI_LLM_BACKEND", "mock")
        monkeypatch.setattr("syssathi.host.config.LLM_BACKEND", "mock")

    def test_get_index_contains_nonce_and_no_approval_token(self):
        with TestClient(app) as client:
            resp = client.get("/")
            assert resp.status_code == 200
            assert "SysSathi" in resp.text
            assert 'meta name="syssathi-nonce"' in resp.text
            # Hard requirement: The approval token must NEVER reach the browser
            assert "SYSSATHI_APPROVAL_TOKEN" not in resp.text

    def test_websocket_talk_offline(self):
        with TestClient(app) as client:
            with client.websocket_connect("/ws/talk") as ws:
                # Send EOF to signal end of user speech
                ws.send_text('{"type": "eof"}')

                # Receive transcript
                msg1 = ws.receive_json()
                assert msg1["type"] == "transcript"

                # Receive assistant reply
                msg2 = ws.receive_json()
                assert msg2["type"] == "reply"
                assert len(msg2["text"].split()) <= 40

    def test_approve_security_checks(self):
        with TestClient(app) as client:
            # 1. Missing nonce -> 403
            resp = client.post("/api/approve")
            assert resp.status_code == 403

            # 2. Wrong nonce -> 403
            resp = client.post("/api/approve", headers={"X-SysSathi-Nonce": "wrong"})
            assert resp.status_code == 403

            # 3. Foreign Origin -> 403
            index_resp = client.get("/")
            import re
            m = re.search(r'content="([a-f0-9]{32})"', index_resp.text)
            assert m, "Nonce not found in index"
            nonce = m.group(1)

            resp = client.post(
                "/api/approve",
                headers={
                    "X-SysSathi-Nonce": nonce,
                    "Origin": "http://malicious-attacker.com",
                },
            )
            assert resp.status_code == 403

            # 4. Correct nonce and origin, but no pending proposal -> 400
            resp = client.post(
                "/api/approve",
                headers={
                    "X-SysSathi-Nonce": nonce,
                    "Origin": "http://127.0.0.1:8000",
                    "Host": "127.0.0.1:8000",
                },
            )
            assert resp.status_code == 400

