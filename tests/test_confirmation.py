"""Tests for confirmation message formatting and re-measure speech."""

from __future__ import annotations

from syssathi.web.confirmation import format_remeasure_reply


class TestConfirmationSpeech:
    def test_ram_dropped(self):
        exec_res = {
            "closed_count": 14,
            "skipped_count": 0,
            "failed_count": 0,
            "diagnosis": {"ram_used_pct": 64.2},
        }
        before = {"ram_used_pct": 91.0}
        reply = format_remeasure_reply(exec_res, before)
        assert "RAM 91% se 64% ho gaya" in reply
        assert len(reply.split()) <= 40

    def test_ram_did_not_drop(self):
        exec_res = {
            "closed_count": 2,
            "skipped_count": 0,
            "failed_count": 0,
            "diagnosis": {"ram_used_pct": 91.0},
        }
        before = {"ram_used_pct": 91.0}
        reply = format_remeasure_reply(exec_res, before)
        assert "Processes band ho gaye, par RAM 91% hi rahi" in reply
        assert len(reply.split()) <= 40

    def test_skipped_and_failed_counts(self):
        exec_res = {
            "closed_count": 5,
            "skipped_count": 2,
            "failed_count": 1,
            "diagnosis": {"ram_used_pct": 70.0},
        }
        before = {"ram_used_pct": 88.0}
        reply = format_remeasure_reply(exec_res, before)
        assert "2 processes skip hue" in reply
        assert "1 processes close hone me fail hue" in reply

    def test_expired_proposal(self):
        exec_res = {"refused": True, "reason": "proposal expired"}
        reply = format_remeasure_reply(exec_res, None)
        assert "Proposal expire ho gaya" in reply

    def test_reused_action_id(self):
        exec_res = {"refused": True, "reason": "action_id already used"}
        reply = format_remeasure_reply(exec_res, None)
        assert "pehle hi execute ho chuka hai" in reply

    def test_raw_execute_action_schema(self):
        exec_res = {
            "closed": 14,
            "skipped": 0,
            "failed": 0,
            "fresh_diagnosis": {"ram_used_pct": 64.2},
        }
        before = {"ram_used_pct": 91.0}
        reply = format_remeasure_reply(exec_res, before)
        assert "RAM 91% se 64% ho gaya" in reply
        assert len(reply.split()) <= 40

