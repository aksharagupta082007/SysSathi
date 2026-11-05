"""Close actions — propose_close and execute_action."""

from __future__ import annotations

import asyncio
import hmac
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

from syssathi.mcp_server.audit import log_event
from syssathi.mcp_server.policy import (
    get_protected_pids,
    is_protected,
    normalize_process_name,
)
from syssathi.mcp_server.sanitize import sanitize

PROPOSAL_EXPIRY_S = 60

# In-memory proposal store (keyed by action_id)
_proposals: dict[str, Proposal] = {}


@dataclass
class Proposal:
    action_id: str
    group: str
    snapshot: list[tuple[int, str, float]]  # (pid, name, create_time)
    created_at: float
    expires_at: float
    used: bool = False
    description: str = ""


def _get_approval_token() -> str | None:
    return os.environ.get("SYSSATHI_APPROVAL_TOKEN")


def _find_group_processes(group_name: str) -> list[tuple[int, str, float]]:
    """Find all processes matching group_name. Returns (pid, name, create_time)."""
    import psutil

    normalized = normalize_process_name(group_name)
    matches: list[tuple[int, str, float]] = []
    for proc in psutil.process_iter(["name"]):
        try:
            pname = proc.info.get("name") or ""
            if normalize_process_name(pname) == normalized:
                matches.append((proc.pid, pname, proc.create_time()))
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            continue
    return matches


def propose_close(
    group_name: str,
    *,
    _now: Callable[[], float] | None = None,
) -> dict[str, Any]:
    """Propose closing a process group. Returns proposal or refusal."""
    now = (_now or time.time)()
    normalized = normalize_process_name(group_name)
    sanitized = sanitize(normalized)

    # Check if protected by name
    if is_protected(group_name):
        log_event(
            tool="propose_close",
            group=sanitized,
            result="refused_protected",
        )
        return {"refused": True, "reason": f"'{sanitized}' is a protected process"}

    # Check if any processes are actually running
    snapshot = _find_group_processes(group_name)
    if not snapshot:
        log_event(
            tool="propose_close",
            group=sanitized,
            result="refused_not_running",
        )
        return {"refused": True, "reason": f"'{sanitized}' is not running"}

    # Check if any PIDs are protected
    protected_pids = get_protected_pids()
    protected_in_snapshot = [pid for pid, _, _ in snapshot if pid in protected_pids]
    if protected_in_snapshot:
        log_event(
            tool="propose_close",
            group=sanitized,
            pids=protected_in_snapshot,
            result="refused_protected_pid",
        )
        return {"refused": True, "reason": f"'{sanitized}' contains protected PIDs"}

    # Build proposal
    action_id = uuid.uuid4().hex
    total_ram_mb = _get_group_ram_mb(snapshot)
    description = (
        f"Close {sanitized}: {len(snapshot)} process{'es' if len(snapshot) != 1 else ''}, "
        f"{total_ram_mb:.1f} MB. Unsaved work may be lost."
    )

    proposal = Proposal(
        action_id=action_id,
        group=sanitized,
        snapshot=snapshot,
        created_at=now,
        expires_at=now + PROPOSAL_EXPIRY_S,
        description=description,
    )
    _proposals[action_id] = proposal

    log_event(
        tool="propose_close",
        action_id=action_id,
        group=sanitized,
        pids=[pid for pid, _, _ in snapshot],
        result="proposed",
    )

    return {
        "action_id": action_id,
        "description": description,
        "expires_in_s": PROPOSAL_EXPIRY_S,
    }


def _get_group_ram_mb(snapshot: list[tuple[int, str, float]]) -> float:
    """Sum RSS of processes in snapshot."""
    import psutil

    total = 0.0
    for pid, _, _ in snapshot:
        try:
            total += psutil.Process(pid).memory_info().rss / (1024 * 1024)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return total


async def execute_action(
    action_id: str,
    approval_token: str,
    *,
    _now: Callable[[], float] | None = None,
) -> dict[str, Any]:
    """Execute a previously proposed close action."""
    now = (_now or time.time)()

    # Check token is set
    expected_token = _get_approval_token()
    if not expected_token:
        log_event(
            tool="execute_action",
            action_id=action_id,
            result="refused_no_token",
        )
        return {"refused": True, "reason": "Approval token not configured"}

    # Constant-time token comparison
    if not hmac.compare_digest(approval_token, expected_token):
        log_event(
            tool="execute_action",
            action_id=action_id,
            result="refused_wrong_token",
        )
        return {"refused": True, "reason": "Invalid approval token"}

    # Check proposal exists
    proposal = _proposals.get(action_id)
    if proposal is None:
        log_event(
            tool="execute_action",
            action_id=action_id,
            result="refused_unknown_id",
        )
        return {"refused": True, "reason": "Unknown action_id"}

    # Check not expired
    if now >= proposal.expires_at:
        log_event(
            tool="execute_action",
            action_id=action_id,
            group=proposal.group,
            result="refused_expired",
        )
        return {"refused": True, "reason": "Proposal has expired"}

    # Check not already used
    if proposal.used:
        log_event(
            tool="execute_action",
            action_id=action_id,
            group=proposal.group,
            result="refused_reused",
        )
        return {"refused": True, "reason": "Proposal has already been executed"}

    # Mark used immediately to prevent concurrent re-use
    proposal.used = True

    # Execute the close
    closed, skipped, failed = await asyncio.to_thread(
        _execute_close_sync, proposal.snapshot
    )

    log_event(
        tool="execute_action",
        action_id=action_id,
        group=proposal.group,
        pids=[pid for pid, _, _ in proposal.snapshot],
        result=f"executed: closed={closed} skipped={skipped} failed={failed}",
    )

    # Fresh diagnosis
    from syssathi.mcp_server.diagnose import run_diagnosis
    fresh = await run_diagnosis()

    return {
        "closed": closed,
        "skipped": skipped,
        "failed": failed,
        "fresh_diagnosis": fresh,
    }


def _execute_close_sync(
    snapshot: list[tuple[int, str, float]],
) -> tuple[int, int, int]:
    """Terminate/kill processes in snapshot. Returns (closed, skipped, failed)."""
    import psutil

    closed = 0
    skipped = 0
    failed = 0

    procs_to_kill: list[psutil.Process] = []

    for pid, expected_name, expected_create_time in snapshot:
        try:
            proc = psutil.Process(pid)
            # Re-check name and create_time still match
            if proc.name() != expected_name or proc.create_time() != expected_create_time:
                skipped += 1
                continue
            proc.terminate()
            procs_to_kill.append(proc)
        except psutil.NoSuchProcess:
            skipped += 1
        except psutil.AccessDenied:
            failed += 1

    # Wait up to 3s for graceful termination
    _, alive = psutil.wait_procs(procs_to_kill, timeout=3)

    # Kill survivors
    for proc in alive:
        try:
            proc.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            failed += 1
            continue

    closed = len(procs_to_kill) - len(alive) + len(alive)  # all attempted
    # Recount properly: closed = terminated successfully
    closed = 0
    for proc in procs_to_kill:
        try:
            proc.wait(timeout=0)  # already dead
            closed += 1
        except psutil.TimeoutExpired:
            failed += 1
        except psutil.NoSuchProcess:
            closed += 1  # already gone

    return closed, skipped, failed


def clear_proposals() -> None:
    """Clear all proposals. For testing only."""
    _proposals.clear()

