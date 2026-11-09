"""Opt-in, local-only telemetry and performance metrics dashboard (Phase F §8).

Strictly opt-in via ENABLE_TELEMETRY.
Stores timing percentiles and tool counts locally in timings.jsonl.
Never records raw user speech or text queries.
"""

from __future__ import annotations

import json
import logging
import statistics
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from platformdirs import user_data_dir

from syssathi.host.config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class TurnTelemetryRecord:
    """Anonymous operational metrics for a completed conversation turn."""

    timestamp: str
    session_id: str
    route: str
    tool_called: str | None
    filler_ms: float | None
    first_sentence_ms: float | None
    total_ms: float
    language: str
    grounding_status: str  # "grounded" | "fallback_used" | "unverified"


def get_telemetry_file_path() -> Path:
    """Return local path to timings.jsonl."""
    base_dir = Path(user_data_dir("syssathi", appauthor=False))
    base_dir.mkdir(parents=True, exist_ok=True)
    return base_dir / "timings.jsonl"


def is_telemetry_enabled() -> bool:
    """Check if telemetry is enabled via settings or environment."""
    return bool(get_settings().ENABLE_TELEMETRY)


def record_turn_telemetry(
    session_id: str,
    route: str,
    total_ms: float,
    tool_called: str | None = None,
    filler_ms: float | None = None,
    first_sentence_ms: float | None = None,
    language: str = "hi",
    grounding_status: str = "grounded",
    file_path: Path | None = None,
) -> None:
    """Record turn metrics if opt-in telemetry is enabled."""
    if not is_telemetry_enabled():
        return

    record = TurnTelemetryRecord(
        timestamp=datetime.now(timezone.utc).isoformat(),
        session_id=session_id[:8] if session_id else "anon",
        route=route,
        tool_called=tool_called,
        filler_ms=round(filler_ms, 1) if filler_ms is not None else None,
        first_sentence_ms=round(first_sentence_ms, 1) if first_sentence_ms is not None else None,
        total_ms=round(total_ms, 1),
        language=language,
        grounding_status=grounding_status,
    )

    path = file_path or get_telemetry_file_path()
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(record), ensure_ascii=False) + "\n")
    except Exception as e:
        logger.warning("Failed to write local telemetry: %s", e)


def compute_summary_stats(file_path: Path | None = None) -> dict[str, Any]:
    """Compute p50/p95 latency and operational summary from local log."""
    path = file_path or get_telemetry_file_path()
    if not path.exists():
        return {
            "total_turns": 0,
            "message": "No telemetry data recorded yet. Enable via ENABLE_TELEMETRY=true.",
        }

    records: list[dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except Exception:
                    pass

    if not records:
        return {"total_turns": 0, "message": "Log file is empty."}

    total_times = [r["total_ms"] for r in records if "total_ms" in r]
    filler_times = [r["filler_ms"] for r in records if r.get("filler_ms") is not None]
    sentence_times = [r["first_sentence_ms"] for r in records if r.get("first_sentence_ms") is not None]

    def _p50(data: list[float]) -> float:
        return float(statistics.median(data)) if data else 0.0

    def _p95(data: list[float]) -> float:
        if not data:
            return 0.0
        s = sorted(data)
        idx = int(round(0.95 * (len(s) - 1)))
        return float(s[idx])

    tools_counter: dict[str, int] = {}
    grounded_count = 0
    fallback_count = 0

    for r in records:
        t = r.get("tool_called")
        if t:
            tools_counter[t] = tools_counter.get(t, 0) + 1
        status = r.get("grounding_status")
        if status == "grounded":
            grounded_count += 1
        elif status == "fallback_used":
            fallback_count += 1

    grounding_rate = (
        (grounded_count + fallback_count) / len(records) * 100.0 if records else 100.0
    )

    p95_filler = _p95(filler_times)
    p95_sentence = _p95(sentence_times)

    return {
        "total_turns": len(records),
        "p50_total_ms": _p50(total_times),
        "p95_total_ms": _p95(total_times),
        "p50_filler_ms": _p50(filler_times),
        "p95_filler_ms": p95_filler,
        "p50_first_sentence_ms": _p50(sentence_times),
        "p95_first_sentence_ms": p95_sentence,
        "tools_breakdown": tools_counter,
        "grounding_pass_rate_pct": round(grounding_rate, 1),
        "targets": {
            "filler_under_1_5s": p95_filler < 1500.0 if filler_times else True,
            "sentence_under_4s": p95_sentence < 4000.0 if sentence_times else True,
            "grounding_100_pct": grounding_rate >= 99.9,
        },
    }


def render_dashboard_text(stats: dict[str, Any]) -> str:
    """Format operational summary into a clean terminal report."""
    if stats.get("total_turns", 0) == 0:
        return f"\n[Telemetry Dashboard]\n{stats.get('message', 'No data.')}\n"

    lines = [
        "",
        "=" * 60,
        "            SysSathi Local Telemetry Dashboard",
        "=" * 60,
        f"Total Recorded Turns:       {stats['total_turns']}",
        f"Grounded Claim Rate:        {stats['grounding_pass_rate_pct']}% (Target: 100%)",
        "",
        "Latency Metrics (p50 / p95):",
        f"  • Filler Latency:         {stats['p50_filler_ms']:.0f} ms / {stats['p95_filler_ms']:.0f} ms (Target: < 1500ms)",
        f"  • First Sentence Latency: {stats['p50_first_sentence_ms']:.0f} ms / {stats['p95_first_sentence_ms']:.0f} ms (Target: < 4000ms)",
        f"  • Total Turn Duration:    {stats['p50_total_ms']:.0f} ms / {stats['p95_total_ms']:.0f} ms",
        "",
        "Tool Calls Executed:",
    ]

    for tool, count in stats.get("tools_breakdown", {}).items():
        lines.append(f"  • {tool:<26} : {count}")

    lines.extend([
        "",
        "Target Compliance:",
        f"  • Filler SLA (< 1.5s):     {'PASS' if stats['targets']['filler_under_1_5s'] else 'WARN'}",
        f"  • Speech SLA (< 4.0s):     {'PASS' if stats['targets']['sentence_under_4s'] else 'WARN'}",
        f"  • Grounding SLA (100%):    {'PASS' if stats['targets']['grounding_100_pct'] else 'WARN'}",
        "=" * 60,
        "",
    ])

    return "\n".join(lines)

