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
from syssathi.schemas import ExecutionResult, Proposal as ProposalSchema, Refusal, RefusalCode

PROPOSAL_EXPIRY_S = 60

# In-memory proposal store (keyed by action_id)
_proposals: dict[str, Proposal] = {}

# S5: Curated safe closable applications (browsers, chat, media, test dummies)
CURATED_SAFE_CLOSABLE: set[str] = {
    # Browsers
    "chrome", "google chrome", "msedge", "edge", "microsoft edge",
    "firefox", "brave", "opera", "vivaldi", "safari", "chromium",
    # Chat / Meetings
    "slack", "discord", "teams", "microsoft teams", "telegram",
    "whatsapp", "signal", "zoom", "skype",
    # Media
    "spotify", "vlc", "itunes", "foobar2000", "wmplayer", "mpv",
    # Safe Utilities / Test dummies
    "notepad", "calculator", "calc", "ping", "dummy", "sleep",
}

# Groups seen in recent diagnosis or top processes
_recent_groups: set[str] = set()


def record_seen_groups(groups: list[str]) -> None:
    """Record group names seen in recent diagnosis or top processes."""
    for g in groups:
        if g:
            _recent_groups.add(normalize_process_name(g))


def clear_seen_groups() -> None:
    """Clear recorded seen groups (for testing)."""
    _recent_groups.clear()


@dataclass
class Proposal:
    action_id: str
    group: str
    snapshot: list[tuple[int, str, float]]  # (pid, name, create_time)
    created_at: float
    expires_at: float
    used: bool = False
    description: str = ""


def _purge_proposals(now: float) -> None:
    """Purge expired proposals and cap in-memory store at 32."""
    expired = [aid for aid, p in _proposals.items() if now >= p.expires_at]
    for aid in expired:
        _proposals.pop(aid, None)
    if len(_proposals) > 32:
        sorted_ids = sorted(_proposals.keys(), key=lambda aid: _proposals[aid].created_at)
        for aid in sorted_ids[: len(_proposals) - 32]:
            _proposals.pop(aid, None)


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
    _purge_proposals(now)
    normalized = normalize_process_name(group_name)
    sanitized = sanitize(normalized)

    # Check if protected by name
    if is_protected(group_name):
        log_event(
            tool="propose_close",
            group=sanitized,
            result="refused_protected",
        )
        return Refusal(
            code=RefusalCode.PROTECTED.value,
            reason=f"'{sanitized}' is a protected process",
        ).model_dump()

    # Check if any processes are actually running
    snapshot = _find_group_processes(group_name)
    if not snapshot:
        log_event(
            tool="propose_close",
            group=sanitized,
            result="refused_not_running",
        )
        return Refusal(
            code=RefusalCode.NOT_RUNNING.value,
            reason=f"'{sanitized}' is not running",
        ).model_dump()

    # S5: Require group to appear in latest diagnosis or curated safe allowlist
    if normalized not in CURATED_SAFE_CLOSABLE and normalized not in _recent_groups:
        log_event(
            tool="propose_close",
            group=sanitized,
            result="refused_not_in_diagnosis",
        )
        return Refusal(
            code=RefusalCode.NOT_IN_DIAGNOSIS.value,
            reason=f"'{sanitized}' was not found in the latest diagnosis. Please confirm the exact app name in the UI.",
        ).model_dump()

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
        return Refusal(
            code=RefusalCode.PROTECTED_PID.value,
            reason=f"'{sanitized}' contains protected PIDs",
        ).model_dump()

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

    return ProposalSchema(
        action_id=action_id,
        description=description,
        expires_in_s=PROPOSAL_EXPIRY_S,
        group=sanitized,
    ).model_dump()


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
        return Refusal(
            code=RefusalCode.NO_TOKEN.value,
            reason="Approval token not configured",
        ).model_dump()

    # Constant-time token comparison
    if not hmac.compare_digest(approval_token, expected_token):
        log_event(
            tool="execute_action",
            action_id=action_id,
            result="refused_wrong_token",
        )
        return Refusal(
            code=RefusalCode.BAD_TOKEN.value,
            reason="Invalid approval token",
        ).model_dump()

    # Check proposal exists
    proposal = _proposals.get(action_id)
    if proposal is None:
        log_event(
            tool="execute_action",
            action_id=action_id,
            result="refused_unknown_id",
        )
        return Refusal(
            code=RefusalCode.UNKNOWN_ID.value,
            reason="Unknown action_id",
        ).model_dump()

    # Check not expired
    if now >= proposal.expires_at:
        log_event(
            tool="execute_action",
            action_id=action_id,
            group=proposal.group,
            result="refused_expired",
        )
        return Refusal(
            code=RefusalCode.EXPIRED.value,
            reason="Proposal has expired",
        ).model_dump()

    # Check not already used
    if proposal.used:
        log_event(
            tool="execute_action",
            action_id=action_id,
            group=proposal.group,
            result="refused_reused",
        )
        return Refusal(
            code=RefusalCode.REUSED.value,
            reason="Proposal has already been executed",
        ).model_dump()

    # S6: Re-check protected PIDs at execute time
    protected_pids = get_protected_pids()
    protected_in_exec = [pid for pid, _, _ in proposal.snapshot if pid in protected_pids]
    if protected_in_exec:
        log_event(
            tool="execute_action",
            action_id=action_id,
            group=proposal.group,
            pids=protected_in_exec,
            result="refused_protected_pid",
        )
        return Refusal(
            code=RefusalCode.PROTECTED_PID.value,
            reason=f"'{proposal.group}' contains protected PIDs",
        ).model_dump()

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

    _purge_proposals(now)

    return ExecutionResult(
        closed=closed,
        skipped=skipped,
        failed=failed,
        fresh_diagnosis=fresh,
    ).model_dump()


def _execute_close_sync(
    snapshot: list[tuple[int, str, float]],
) -> tuple[int, int, int]:
    """Terminate/kill processes in snapshot. Returns (closed, skipped, failed)."""
    import psutil

    skipped = 0
    failed = 0
    procs_to_terminate: list[psutil.Process] = []

    for pid, expected_name, expected_create_time in snapshot:
        try:
            proc = psutil.Process(pid)
            # Re-check name and create_time still match
            if proc.name() != expected_name or proc.create_time() != expected_create_time:
                skipped += 1
                continue
            proc.terminate()
            procs_to_terminate.append(proc)
        except psutil.NoSuchProcess:
            skipped += 1
        except psutil.AccessDenied:
            failed += 1

    # Wait up to 3s for graceful termination
    gone_term, alive = psutil.wait_procs(procs_to_terminate, timeout=3)
    closed = len(gone_term)

    # Kill survivors
    survivors_to_wait: list[psutil.Process] = []
    for proc in alive:
        try:
            proc.kill()
            survivors_to_wait.append(proc)
        except psutil.NoSuchProcess:
            closed += 1
        except psutil.AccessDenied:
            failed += 1

    if survivors_to_wait:
        gone_kill, still_alive = psutil.wait_procs(survivors_to_wait, timeout=2)
        closed += len(gone_kill)
        failed += len(still_alive)

    return closed, skipped, failed


def clear_proposals() -> None:
    """Clear all proposals and seen groups. For testing only."""
    _proposals.clear()
    clear_seen_groups()

