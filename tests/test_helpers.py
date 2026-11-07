"""Test helpers for SysSathi test suites, including Addendum A2 number verification."""

from __future__ import annotations

import re
from typing import Any


def extract_numbers_from_text(text: str) -> list[float]:
    """Extract all numbers (integers and floats) from a text string.
    
    Ignores punctuation and trailing symbols like '%'.
    """
    # Matches integers or decimal floats: e.g., 91, 91.2, 3.1
    matches = re.findall(r"\b\d+(?:\.\d+)?\b", text)
    return [float(m) for m in matches]


def collect_allowed_numbers(findings: dict[str, Any]) -> set[float]:
    """Collect all valid numbers from findings JSON per Addendum A2.
    
    Addendum A2:
    A number in a reply is valid if:
      1. It equals a number in the findings JSON.
      2. It equals one rounded to a whole number.
      3. It equals a group's ram_mb divided by 1000 rounded to one decimal.
    """
    allowed: set[float] = set()

    def _add_num(val: Any) -> None:
        if isinstance(val, (int, float)):
            f_val = float(val)
            allowed.add(f_val)
            allowed.add(float(round(f_val)))
            allowed.add(round(f_val, 1))

    # Top-level numeric values
    for k in [
        "cpu_avg_pct",
        "cpu_peak_pct",
        "ram_used_pct",
        "ram_total_gb",
        "disk_free_pct",
        "disk_mb_per_s",
        "startup_apps",
    ]:
        if k in findings:
            _add_num(findings[k])

    # Top groups
    for g in findings.get("top_groups", []):
        if "procs" in g:
            _add_num(g["procs"])
        if "ram_mb" in g:
            _add_num(g["ram_mb"])
            # Rule 3: ram_mb divided by 1000 rounded to one decimal (e.g. 3100 -> 3.1)
            gb_val = round(g["ram_mb"] / 1000.0, 1)
            allowed.add(gb_val)
            allowed.add(float(round(gb_val)))
        if "cpu_pct" in g:
            _add_num(g["cpu_pct"])

    return allowed


def verify_reply_numbers(reply: str, findings: dict[str, Any]) -> tuple[bool, list[float]]:
    """Check that every number in reply is allowed per Addendum A2.
    
    Returns (is_valid, invalid_numbers).
    """
    numbers = extract_numbers_from_text(reply)
    if not numbers:
        return True, []

    allowed = collect_allowed_numbers(findings)
    invalid: list[float] = []

    for num in numbers:
        # Check against allowed values (float precision tolerance)
        matched = False
        for a in allowed:
            if abs(num - a) < 1e-4:
                matched = True
                break
        if not matched:
            invalid.append(num)

    return len(invalid) == 0, invalid

