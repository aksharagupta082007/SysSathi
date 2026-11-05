"""Process grouping and sampling — pure logic separated from psutil."""

from __future__ import annotations

import asyncio
import platform
import sys
from typing import Any

from syssathi.mcp_server.policy import normalize_process_name
from syssathi.mcp_server.sanitize import sanitize


def group_process_list(
    raw_entries: list[dict[str, Any]],
    cpu_count: int,
) -> list[dict[str, Any]]:
    """Group processes by normalized name and return top 5 by RAM.

    Each raw_entry: {"name": str, "rss_bytes": int, "cpu_pct": float}
    cpu_pct is per-process (can exceed 100 on multi-core), divided by cpu_count.
    """
    groups: dict[str, dict[str, Any]] = {}
    for entry in raw_entries:
        raw_name = entry["name"]
        key = normalize_process_name(raw_name)
        key = sanitize(key)
        if key not in groups:
            groups[key] = {"name": key, "procs": 0, "ram_mb": 0.0, "cpu_pct": 0.0}
        g = groups[key]
        g["procs"] += 1
        g["ram_mb"] += entry["rss_bytes"] / (1024 * 1024)
        g["cpu_pct"] += entry["cpu_pct"] / cpu_count

    result = sorted(groups.values(), key=lambda g: g["ram_mb"], reverse=True)[:5]
    # Round for clean output
    for g in result:
        g["ram_mb"] = round(g["ram_mb"], 1)
        g["cpu_pct"] = round(g["cpu_pct"], 1)
    return result


def _sample_processes_sync() -> tuple[list[dict[str, Any]], int]:
    """Sample all processes via psutil. Returns (entries, cpu_count).

    Skips processes raising AccessDenied or NoSuchProcess.
    Must be called after priming cpu_percent().
    """
    import psutil

    cpu_count = psutil.cpu_count() or 1
    entries: list[dict[str, Any]] = []
    for proc in psutil.process_iter(["name", "memory_info", "cpu_percent"]):
        try:
            info = proc.info
            name = info.get("name") or ""
            mem = info.get("memory_info")
            rss = mem.rss if mem else 0
            cpu = info.get("cpu_percent") or 0.0
            entries.append({"name": name, "rss_bytes": rss, "cpu_pct": cpu})
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            continue
    return entries, cpu_count


async def sample_processes() -> list[dict[str, Any]]:
    """Sample processes in a worker thread and return top-5 groups."""
    entries, cpu_count = await asyncio.to_thread(_sample_processes_sync)
    return group_process_list(entries, cpu_count)


def prime_cpu_percent() -> None:
    """Prime per-process cpu_percent so the next read is meaningful."""
    import psutil

    for proc in psutil.process_iter(["cpu_percent"]):
        try:
            proc.cpu_percent()
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            continue

