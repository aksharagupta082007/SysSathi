"""Timing — one JSON line per request to logs/timings.jsonl."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any


def _default_logs_dir() -> Path:
    """Return the default logs directory."""
    from syssathi.host.config import LOGS_DIR
    return LOGS_DIR


class Timer:
    """Accumulate timing fields for one request and flush to disk."""

    def __init__(self, *, logs_dir: Path | None = None) -> None:
        self._start = time.perf_counter()
        self._fields: dict[str, Any] = {}
        self._logs_dir = logs_dir

    def mark(self, name: str, start_time: float | None = None) -> None:
        """Record a timing field in milliseconds from *start_time* to now.

        If *start_time* is None, records from the request start.
        """
        if start_time is not None:
            ms = (time.perf_counter() - start_time) * 1000
        else:
            ms = (time.perf_counter() - self._start) * 1000
        self._fields[name] = round(ms, 1)

    def set(self, name: str, value: Any) -> None:
        """Set an arbitrary field (e.g. route)."""
        self._fields[name] = value

    def elapsed_ms(self) -> float:
        """Milliseconds since timer creation."""
        return (time.perf_counter() - self._start) * 1000

    @property
    def route(self) -> str | None:
        return self._fields.get("route")

    @property
    def total_ms(self) -> float:
        return self._fields.get("total_ms", round(self.elapsed_ms(), 1))

    def flush(self) -> dict[str, Any]:
        """Record total_ms and append one JSON line to timings.jsonl.

        Returns the full timing record.
        """
        self._fields["total_ms"] = round(self.elapsed_ms(), 1)
        # Ensure Phase 3 keys exist or are preserved if set
        for k in ["stt_ms", "first_sentence_ms", "tts_first_byte_ms"]:
            if k in self._fields:
                self._fields[k] = round(self._fields[k], 1)
        logs_dir = self._logs_dir or _default_logs_dir()
        logs_dir.mkdir(parents=True, exist_ok=True)
        path = logs_dir / "timings.jsonl"
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(self._fields, ensure_ascii=False) + "\n")
        return dict(self._fields)

