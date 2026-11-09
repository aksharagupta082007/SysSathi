"""Tests for actions.py — propose_close and execute_action.

All tests that close a process use only a dummy child: ping -t 127.0.0.1
started with an argument list and no shell, group name "ping".
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import time
from unittest import mock

import psutil
import pytest

from syssathi.mcp_server.actions import (
    clear_proposals,
    execute_action,
    propose_close,
)
from syssathi.mcp_server.policy import normalize_process_name

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _clean_proposals():
    """Clear proposal store before and after each test."""
    clear_proposals()
    yield
    clear_proposals()


@pytest.fixture
def dummy_ping():
    """Start a dummy ping child process. Kill it in teardown.

    The group name is 'ping' (normalize_process_name('PING.EXE') == 'ping').
    """
    kwargs = {
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }
    if hasattr(subprocess, "CREATE_NO_WINDOW"):
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

    cmd = ["ping", "-t", "127.0.0.1"] if os.name == "nt" else ["ping", "127.0.0.1"]
    proc = subprocess.Popen(cmd, **kwargs)
    # Verify it's running and the group is "ping"
    ps = psutil.Process(proc.pid)
    assert normalize_process_name(ps.name()) == "ping", (
        f"Expected group 'ping', got '{normalize_process_name(ps.name())}'"
    )
    yield proc
    # Teardown: kill if still alive
    try:
        ps_proc = psutil.Process(proc.pid)
        ps_proc.kill()
        ps_proc.wait(timeout=5)
    except (psutil.NoSuchProcess, OSError):
        pass


@pytest.fixture
def token():
    """Set a known approval token in the environment."""
    tok = "test_token_abc123"
    with mock.patch.dict(os.environ, {"SYSSATHI_APPROVAL_TOKEN": tok}):
        yield tok


# ---------------------------------------------------------------------------
# propose_close tests
# ---------------------------------------------------------------------------

class TestProposeCloseRefusals:
    def test_refuses_protected_group(self):
        result = propose_close("explorer")
        assert result["refused"] is True
        assert "protected" in result["reason"].lower()

    def test_refuses_protected_group_case_insensitive(self):
        result = propose_close("Explorer.exe")
        assert result["refused"] is True

    def test_refuses_python_group(self):
        result = propose_close("python3.11")
        assert result["refused"] is True

    def test_refuses_unknown_group(self):
        result = propose_close("zzznonexistent_app_12345")
        assert result["refused"] is True
        assert "not running" in result["reason"].lower()

    def test_refuses_svchost(self):
        result = propose_close("svchost")
        assert result["refused"] is True

    def test_refuses_system(self):
        result = propose_close("System")
        assert result["refused"] is True

    def test_refuses_running_group_not_in_diagnosis_or_allowlist(self):
        from syssathi.mcp_server.actions import record_seen_groups
        with mock.patch("syssathi.mcp_server.actions._find_group_processes", return_value=[(9999, "backupagent", 1000.0)]):
            res = propose_close("backupagent")
            assert res.get("refused") is True
            assert res.get("code") == "NOT_IN_DIAGNOSIS"

            # Once seen in diagnosis, it is allowed
            record_seen_groups(["backupagent"])
            res2 = propose_close("backupagent")
            assert "action_id" in res2


class TestProposeCloseSuccess:
    def test_proposes_ping(self, dummy_ping, token):
        result = propose_close("ping")
        assert "action_id" in result
        assert "description" in result
        assert result["expires_in_s"] == 60
        assert "ping" in result["description"].lower()

    def test_proposal_snapshot_contains_pid(self, dummy_ping, token):
        from syssathi.mcp_server.actions import _proposals
        result = propose_close("ping")
        proposal = _proposals[result["action_id"]]
        pids = [pid for pid, _, _ in proposal.snapshot]
        assert dummy_ping.pid in pids


# ---------------------------------------------------------------------------
# execute_action tests
# ---------------------------------------------------------------------------

class TestExecuteActionRefusals:
    def test_refuses_no_token(self, dummy_ping):
        """Token env var unset → refuse everything."""
        with mock.patch.dict(os.environ, {}, clear=True):
            # Remove the key entirely
            os.environ.pop("SYSSATHI_APPROVAL_TOKEN", None)
            result = propose_close("ping")
            action_id = result["action_id"]
            exec_result = asyncio.run(
                execute_action(action_id, "anything")
            )
            assert exec_result["refused"] is True
            assert "not configured" in exec_result["reason"].lower()

    def test_refuses_wrong_token(self, dummy_ping, token):
        result = propose_close("ping")
        action_id = result["action_id"]
        exec_result = asyncio.run(
            execute_action(action_id, "wrong_token")
        )
        assert exec_result["refused"] is True
        assert "invalid" in exec_result["reason"].lower()

    def test_refuses_unknown_action_id(self, token):
        exec_result = asyncio.run(
            execute_action("nonexistent_id", token)
        )
        assert exec_result["refused"] is True
        assert "unknown" in exec_result["reason"].lower()

    def test_refuses_expired_proposal(self, dummy_ping, token):
        """Use injected clock to simulate expiry without waiting 60s."""
        now = time.time()
        result = propose_close("ping", _now=lambda: now)
        action_id = result["action_id"]
        # Execute with time far in the future (past expiry)
        exec_result = asyncio.run(
            execute_action(action_id, token, _now=lambda: now + 61)
        )
        assert exec_result["refused"] is True
        assert "expired" in exec_result["reason"].lower()

    def test_refuses_reused_action_id(self, dummy_ping, token):
        result = propose_close("ping")
        action_id = result["action_id"]
        # First execution should succeed
        exec_result = asyncio.run(
            execute_action(action_id, token)
        )
        assert "refused" not in exec_result or exec_result.get("refused") is not True
        # Start a new ping for the re-use test
        # Second execution with same action_id should be refused
        exec_result2 = asyncio.run(
            execute_action(action_id, token)
        )
        assert exec_result2["refused"] is True
        assert "already been executed" in exec_result2["reason"].lower()

    def test_proposals_purged_when_expired(self, dummy_ping):
        from syssathi.mcp_server.actions import _proposals, _purge_proposals, Proposal
        now = time.time()
        # Add expired proposal
        _proposals["exp1"] = Proposal(
            action_id="exp1", group="g", snapshot=[], created_at=now - 100, expires_at=now - 40
        )
        # Add valid proposal
        _proposals["valid1"] = Proposal(
            action_id="valid1", group="g", snapshot=[], created_at=now, expires_at=now + 60
        )
        _purge_proposals(now)
        assert "exp1" not in _proposals
        assert "valid1" in _proposals


class TestExecuteActionSkipChangedCreateTime:
    def test_changed_create_time_is_skipped(self, dummy_ping, token):
        """If create_time changed in snapshot, that entry is skipped, not killed."""
        from syssathi.mcp_server.actions import _proposals
        result = propose_close("ping")
        action_id = result["action_id"]

        # Tamper with the create_time in the snapshot
        proposal = _proposals[action_id]
        original_snapshot = proposal.snapshot
        tampered = [
            (pid, name, create_time + 9999.0)
            for pid, name, create_time in original_snapshot
        ]
        proposal.snapshot = tampered

        exec_result = asyncio.run(
            execute_action(action_id, token)
        )
        # Process should be skipped, not killed
        assert exec_result["skipped"] >= 1
        # Verify the ping is still alive
        assert psutil.pid_exists(dummy_ping.pid)


class TestExecuteActionHappyPath:
    def test_closes_dummy_ping(self, dummy_ping, token):
        """Happy path: closes the dummy ping and returns counts + diagnosis."""
        result = propose_close("ping")
        action_id = result["action_id"]

        exec_result = asyncio.run(
            execute_action(action_id, token)
        )
        assert exec_result.get("refused") is not True
        assert exec_result["closed"] >= 1
        assert "fresh_diagnosis" in exec_result

        # Verify the ping process is gone
        time.sleep(0.5)
        assert not psutil.pid_exists(dummy_ping.pid)

