"""Diagnose slowness — 3-second sampling window with pure logic separated."""

from __future__ import annotations

import asyncio
import os
import platform
import time
from typing import Any

from syssathi.mcp_server.policy import get_thresholds
from syssathi.mcp_server.processes import group_process_list
from syssathi.mcp_server.sanitize import sanitize

# JSON schema for validation
FINDINGS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "cpu_avg_pct": {"type": "number"},
        "cpu_peak_pct": {"type": "number"},
        "ram_used_pct": {"type": "number"},
        "ram_total_gb": {"type": "number"},
        "disk_free_pct": {"type": "number"},
        "disk_mb_per_s": {"type": "number"},
        "top_groups": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "procs": {"type": "integer"},
                    "ram_mb": {"type": "number"},
                    "cpu_pct": {"type": "number"},
                },
                "required": ["name", "procs", "ram_mb", "cpu_pct"],
            },
        },
        "startup_apps": {"type": "integer"},
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "code": {"type": "string"},
                    "message": {"type": "string"},
                    "severity": {"type": "string"},
                },
                "required": ["code", "message", "severity"],
            },
        },
    },
    "required": [
        "cpu_avg_pct",
        "cpu_peak_pct",
        "ram_used_pct",
        "ram_total_gb",
        "disk_free_pct",
        "disk_mb_per_s",
        "top_groups",
        "startup_apps",
        "findings",
    ],
}


def build_findings(
    *,
    cpu_samples: list[float],
    ram_used_pct: float,
    ram_total_gb: float,
    disk_free_pct: float,
    disk_mb_per_s: float,
    top_groups: list[dict[str, Any]],
    startup_count: int,
    thresholds: dict[str, float | int] | None = None,
) -> dict[str, Any]:
    """Build findings JSON from raw measurements (pure, no psutil)."""
    th = thresholds or get_thresholds()

    cpu_avg = round(sum(cpu_samples) / len(cpu_samples), 1) if cpu_samples else 0.0
    cpu_peak = round(max(cpu_samples), 1) if cpu_samples else 0.0

    findings_list: list[dict[str, str]] = []

    if ram_used_pct > th["RAM_HIGH_PCT"]:
        findings_list.append({
            "code": "RAM_HIGH",
            "message": f"RAM above {th['RAM_HIGH_PCT']:.0f}%",
            "severity": "high",
        })
    if disk_free_pct < th["DISK_LOW_PCT"]:
        findings_list.append({
            "code": "DISK_LOW",
            "message": f"Disk free below {th['DISK_LOW_PCT']:.0f}%",
            "severity": "high",
        })
    if startup_count > th["STARTUP_HIGH_COUNT"]:
        findings_list.append({
            "code": "STARTUP_HIGH",
            "message": f"More than {th['STARTUP_HIGH_COUNT']} startup apps",
            "severity": "medium",
        })
    if cpu_avg > th["CPU_HIGH_PCT"]:
        findings_list.append({
            "code": "CPU_HIGH",
            "message": f"CPU above {th['CPU_HIGH_PCT']:.0f}% average",
            "severity": "high",
        })

    return {
        "cpu_avg_pct": cpu_avg,
        "cpu_peak_pct": cpu_peak,
        "ram_used_pct": round(ram_used_pct, 1),
        "ram_total_gb": round(ram_total_gb, 1),
        "disk_free_pct": round(disk_free_pct, 1),
        "disk_mb_per_s": round(disk_mb_per_s, 1),
        "top_groups": top_groups,
        "startup_apps": startup_count,
        "findings": findings_list,
    }


def _sample_sync() -> dict[str, Any]:
    """Run the 3-second sampling window (blocking, call in worker thread).

    The brief says: prime per-process cpu_percent() at the start, read at the
    end, sample overall CPU every 0.5 s.  On a busy machine with ~400 procs,
    priming takes ~1.7 s and reading takes ~1.8 s.  We overlap the 0.5 s CPU
    samples with the per-process read using a background thread so the total
    wall time stays around 3 s (prime ~1.7 s + max(samples, read) ~1.8 s).
    """
    import concurrent.futures

    import psutil

    window_start = time.perf_counter()

    # --- Start of window ---
    # Disk IO at start
    disk_io_start = psutil.disk_io_counters()
    disk_start_bytes = (
        (disk_io_start.read_bytes + disk_io_start.write_bytes) if disk_io_start else 0
    )

    # Prime per-process CPU (first call sets baseline; value is meaningless)
    procs: list = []
    for proc in psutil.process_iter():
        try:
            proc.cpu_percent()
            procs.append(proc)
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            continue

    # Collect overall CPU samples in a background thread while we read
    # per-process data in the main thread.  This overlaps the ~0.5-1.0 s of
    # cpu_percent(interval=…) with the ~1.8 s per-process read.
    prime_elapsed = time.perf_counter() - window_start
    sample_duration = max(0.5, min(1.5, 3.0 - prime_elapsed))
    n_samples = max(1, int(sample_duration / 0.5))

    def _collect_cpu_samples() -> list[float]:
        samples: list[float] = []
        for _ in range(n_samples):
            samples.append(psutil.cpu_percent(interval=0.5))
        return samples

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        cpu_future = pool.submit(_collect_cpu_samples)

        # --- End of window ---
        # Read per-process CPU (meaningful after the gap since priming)
        cpu_count = psutil.cpu_count() or 1
        proc_entries: list[dict[str, Any]] = []
        for proc in procs:
            try:
                with proc.oneshot():
                    name = proc.name()
                    rss = proc.memory_info().rss
                    cpu = proc.cpu_percent()
                proc_entries.append({"name": name, "rss_bytes": rss, "cpu_pct": cpu})
            except (psutil.AccessDenied, psutil.NoSuchProcess):
                continue

        cpu_samples = cpu_future.result(timeout=10)

    top_groups = group_process_list(proc_entries, cpu_count)

    # Disk IO at end
    disk_io_end = psutil.disk_io_counters()
    disk_end_bytes = (
        (disk_io_end.read_bytes + disk_io_end.write_bytes) if disk_io_end else 0
    )
    window_duration = time.perf_counter() - window_start
    # Use actual elapsed for accurate disk throughput
    disk_mb_per_s = (
        (disk_end_bytes - disk_start_bytes) / (1024 * 1024) / window_duration
        if window_duration > 0
        else 0.0
    )

    # RAM
    mem = psutil.virtual_memory()
    ram_used_pct = mem.percent
    ram_total_gb = mem.total / (1024 ** 3)

    # Disk free (system drive)
    sys_drive = os.environ.get("SystemDrive", "C:")
    disk_usage = psutil.disk_usage(sys_drive + "\\")
    disk_free_pct = (disk_usage.free / disk_usage.total) * 100

    return {
        "cpu_samples": cpu_samples,
        "ram_used_pct": ram_used_pct,
        "ram_total_gb": ram_total_gb,
        "disk_free_pct": disk_free_pct,
        "disk_mb_per_s": disk_mb_per_s,
        "top_groups": top_groups,
    }


async def run_diagnosis() -> dict[str, Any]:
    """Run full diagnosis. Returns {"supported": false} on non-Windows."""
    if platform.system() != "Windows":
        return {"supported": False}

    # Run sampling and startup collection concurrently
    from syssathi.mcp_server.startup import list_startup_apps

    raw_task = asyncio.to_thread(_sample_sync)
    startup_task = list_startup_apps()
    raw, startup_result = await asyncio.gather(raw_task, startup_task)

    startup_count = startup_result.get("count", 0)

    return build_findings(
        cpu_samples=raw["cpu_samples"],
        ram_used_pct=raw["ram_used_pct"],
        ram_total_gb=raw["ram_total_gb"],
        disk_free_pct=raw["disk_free_pct"],
        disk_mb_per_s=raw["disk_mb_per_s"],
        top_groups=raw["top_groups"],
        startup_count=startup_count,
    )
