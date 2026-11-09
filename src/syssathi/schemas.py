"""Typed pydantic contracts for SysSathi tools, actions, and diagnostics."""

from __future__ import annotations

from enum import Enum
from typing import Any
from pydantic import BaseModel, Field


class RefusalCode(str, Enum):
    """Machine-readable refusal codes for actions."""
    PROTECTED = "PROTECTED"
    NOT_RUNNING = "NOT_RUNNING"
    NOT_IN_DIAGNOSIS = "NOT_IN_DIAGNOSIS"
    EXPIRED = "EXPIRED"
    REUSED = "REUSED"
    BAD_TOKEN = "BAD_TOKEN"
    NO_TOKEN = "NO_TOKEN"
    UNKNOWN_ID = "UNKNOWN_ID"
    PROTECTED_PID = "PROTECTED_PID"


class ProcessGroup(BaseModel):
    """A group of processes aggregated by name."""
    name: str
    procs: int
    ram_mb: float
    cpu_pct: float


class FindingItem(BaseModel):
    """An individual diagnostic finding item."""
    code: str
    message: str
    severity: str = "high"


class Findings(BaseModel):
    """Full diagnostic result from diagnose_slowness."""
    cpu_avg_pct: float
    cpu_peak_pct: float
    ram_used_pct: float
    ram_total_gb: float
    disk_free_pct: float
    disk_mb_per_s: float
    top_groups: list[ProcessGroup] = Field(default_factory=list)
    startup_apps: int = 0
    findings: list[FindingItem] = Field(default_factory=list)
    window_s: float | None = None
    swap_used_pct: float | None = None


class StartupEntry(BaseModel):
    """A startup application entry."""
    name: str
    source: str
    enabled: bool = True


class StartupReport(BaseModel):
    """Result of list_startup_apps."""
    entries: list[StartupEntry] = Field(default_factory=list)
    count: int = 0


class BatteryReport(BaseModel):
    """Result of get_battery_report."""
    has_battery: bool
    charge_pct: int = 0
    plugged: bool = False
    health_pct: float | None = None
    health_available: bool = False
    unit: str = "mWh"


class Proposal(BaseModel):
    """Successful proposal from propose_close."""
    action_id: str
    description: str
    expires_in_s: int = 60
    group: str = ""


class Refusal(BaseModel):
    """Refusal response when an action or proposal cannot proceed."""
    refused: bool = True
    code: str
    reason: str


class ExecutionResult(BaseModel):
    """Result of execute_action."""
    closed: int
    skipped: int
    failed: int
    fresh_diagnosis: Findings | dict[str, Any] | None = None
