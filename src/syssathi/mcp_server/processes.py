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
    top_n: int | None = 5,
) -> list[dict[str, Any]]:
    """Group processes by normalized name and return groups sorted by RAM.

    Each raw_entry: {"name": str, "rss_bytes": int, "cpu_pct": float}
    cpu_pct is per-process (can exceed 100 on multi-core), divided by cpu_count.
    If top_n is specified, limits output to top_n groups. If None, returns all groups.
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

    result = sorted(groups.values(), key=lambda g: g["ram_mb"], reverse=True)
    # Round for clean output
    for g in result:
        g["ram_mb"] = round(g["ram_mb"], 1)
        g["cpu_pct"] = round(g["cpu_pct"], 1)

    if top_n is not None:
        return result[:top_n]
    return result


def sample_process_table(window_s: float = 0.5) -> tuple[list[dict[str, Any]], int]:
    """Sample all processes via psutil with priming and delay. Returns (entries, cpu_count).

    Primes cpu_percent(), waits window_s, and then reads meaningful cpu_percent() and rss.
    Skips processes raising AccessDenied or NoSuchProcess.
    """
    import time
    import psutil

    cpu_count = psutil.cpu_count() or 1
    procs: list[psutil.Process] = []
    for proc in psutil.process_iter():
        try:
            proc.cpu_percent()
            procs.append(proc)
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            continue

    if window_s > 0:
        time.sleep(window_s)

    entries: list[dict[str, Any]] = []
    for proc in procs:
        try:
            with proc.oneshot():
                name = proc.name()
                mem = proc.memory_info()
                rss = mem.rss if mem else 0
                cpu = proc.cpu_percent()
            entries.append({"name": name, "rss_bytes": rss, "cpu_pct": cpu})
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            continue
    return entries, cpu_count


async def sample_processes(
    window_s: float = 0.5,
    top_n: int | None = None,
) -> list[dict[str, Any]]:
    """Sample processes in a worker thread and return groups."""
    entries, cpu_count = await asyncio.to_thread(sample_process_table, window_s)
    return group_process_list(entries, cpu_count, top_n=top_n)


def prime_cpu_percent() -> None:
    """Prime per-process cpu_percent so the next read is meaningful."""
    import psutil

    for proc in psutil.process_iter(["cpu_percent"]):
        try:
            proc.cpu_percent()
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            continue

