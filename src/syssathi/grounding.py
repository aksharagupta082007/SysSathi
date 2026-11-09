"""Grounding and number verification for LLM responses (Addendum A2)."""

from __future__ import annotations

import re
import unicodedata
from typing import Any


def normalize_digits(text: str) -> str:
    """Convert Unicode decimal digits (Devanagari, Bengali, Arabic-Indic, etc.) to ASCII 0-9."""
    chars: list[str] = []
    for ch in text:
        if unicodedata.category(ch) == "Nd":
            chars.append(str(unicodedata.digit(ch)))
        else:
            chars.append(ch)
    return "".join(chars)


def extract_numbers_from_text(text: str) -> list[float]:
    """Extract all numbers (integers and floats) from text, normalizing Unicode digits."""
    normalized = normalize_digits(text)
    matches = re.findall(r"\b\d+(?:\.\d+)?\b", normalized)
    return [float(m) for m in matches]


_URL_REGEX = re.compile(r"https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+[^\s\)]*")


def extract_urls_from_text(text: str) -> list[str]:
    """Extract all HTTP/HTTPS URLs from text."""
    matches = _URL_REGEX.findall(text)
    # Strip trailing punctuation often caught in sentences
    cleaned: list[str] = []
    for m in matches:
        u = m.rstrip(".,;!?\"'")
        cleaned.append(u)
    return cleaned


def collect_allowed_urls(data: Any) -> set[str]:
    """Recursively collect all URLs from tool result JSON."""
    urls: set[str] = set()

    def _walk(obj: Any) -> None:
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k == "url" and isinstance(v, str) and v.startswith("http"):
                    urls.add(v.rstrip("/"))
                elif isinstance(v, (dict, list)):
                    _walk(v)
        elif isinstance(obj, list):
            for item in obj:
                _walk(item)

    _walk(data)
    return urls


def verify_reply_citations(reply: str, tool_data: dict[str, Any]) -> tuple[bool, list[str]]:
    """Check that every URL cited in reply is present in tool data (Phase D §6.4).

    Returns (is_valid, ungrounded_urls).
    """
    found_urls = extract_urls_from_text(reply)
    if not found_urls:
        return True, []

    allowed_urls = collect_allowed_urls(tool_data)
    # Also allow hostnames
    allowed_hosts = {u.split("://")[-1].split("/")[0].lower() for u in allowed_urls}

    ungrounded: list[str] = []
    for u in found_urls:
        norm = u.rstrip("/")
        host = norm.split("://")[-1].split("/")[0].lower()
        if norm not in allowed_urls and host not in allowed_hosts:
            ungrounded.append(u)

    return len(ungrounded) == 0, ungrounded


def collect_allowed_numbers(data: dict[str, Any]) -> set[float]:
    """Collect all valid numbers from tool data JSON per Addendum A2.

    Addendum A2:
    A number in a reply is valid if:
      1. It equals a number in the tool output JSON.
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

    # Top-level numeric values across findings, battery, startup
    for k in [
        "cpu_avg_pct",
        "cpu_peak_pct",
        "ram_used_pct",
        "ram_total_gb",
        "disk_free_pct",
        "disk_mb_per_s",
        "startup_apps",
        "count",
        "charge_pct",
        "health_pct",
    ]:
        if k in data:
            _add_num(data[k])

    # Top groups in findings
    for g in data.get("top_groups", []):
        if "procs" in g:
            _add_num(g["procs"])
        if "ram_mb" in g:
            _add_num(g["ram_mb"])
            gb_val = round(g["ram_mb"] / 1000.0, 1)
            allowed.add(gb_val)
            allowed.add(float(round(gb_val)))
        if "cpu_pct" in g:
            _add_num(g["cpu_pct"])

    # Process groups list (get_top_processes)
    for g in data.get("groups", []):
        if "procs" in g:
            _add_num(g["procs"])
        if "ram_mb" in g:
            _add_num(g["ram_mb"])
            gb_val = round(g["ram_mb"] / 1000.0, 1)
            allowed.add(gb_val)
            allowed.add(float(round(gb_val)))
        if "cpu_pct" in g:
            _add_num(g["cpu_pct"])

    return allowed


def verify_reply_numbers(reply: str, tool_data: dict[str, Any]) -> tuple[bool, list[float]]:
    """Check that every number in reply is allowed per Addendum A2.

    Returns (is_valid, invalid_numbers).
    """
    numbers = extract_numbers_from_text(reply)
    if not numbers:
        return True, []

    allowed = collect_allowed_numbers(tool_data)
    invalid: list[float] = []

    for num in numbers:
        matched = False
        for a in allowed:
            if abs(num - a) < 1e-4:
                matched = True
                break
        if not matched:
            invalid.append(num)

    return len(invalid) == 0, invalid


def format_template_reply(data: dict[str, Any]) -> str:
    """Format a guaranteed grounded deterministic template reply from tool data."""
    # 1. Top process groups
    if "groups" in data and isinstance(data["groups"], list):
        groups = data["groups"]
        if groups:
            top = groups[0]
            return f"Top process {top.get('name', '')} hai jo {top.get('ram_mb', 0)} MB RAM aur {top.get('cpu_pct', 0)}% CPU le raha hai."
        return "Koi process group nahi mila."

    # 2. Startup apps
    if "entries" in data and "count" in data:
        count = data.get("count", 0)
        names = [e.get("name", "") for e in data.get("entries", [])[:3] if isinstance(e, dict)]
        names_str = ", ".join(names) if names else "koi app nahi"
        return f"Startup mein {count} apps hain: {names_str}."

    # 3. Battery report
    if "charge_pct" in data:
        pct = data.get("charge_pct", 0)
        plugged = "charging par" if data.get("plugged") else "battery par"
        health = f", health {data.get('health_pct')}%" if "health_pct" in data and data.get("health_pct") is not None else ""
        return f"Battery {pct}% charged hai aur {plugged} hai{health}."

    # 4. Tool recommendations
    if "recommendations" in data and isinstance(data["recommendations"], list):
        recs = data["recommendations"]
        if recs:
            r = recs[0]
            tip = f" Tip: {r['download_safety_tips'][0]}" if r.get("download_safety_tips") else ""
            return f"Recommended tool: {r.get('name')} ({r.get('url')}). {r.get('why_recommended')}{tip}"
        return "Is category ke liye koi tool nahi mila."

    # 5. Search sources results
    if "results" in data and isinstance(data["results"], list) and "query" in data:
        results = data["results"]
        if results:
            res = results[0]
            return f"{res.get('title')}: {res.get('summary')} Source: {res.get('url')}"
        return "Curated sources mein is query ka result nahi mila."

    # 6. Term explanation
    if "term" in data and "summary" in data:
        return f"{data.get('title', data['term'])}: {data.get('summary')}"

    # 7. Findings
    findings_list = data.get("findings", [])
    if isinstance(data.get("findings"), dict):
        findings_list = data["findings"].get("findings", [])
        data = data["findings"]

    if not findings_list:
        return "Laptop theek lag raha hai, koi problem nahi dikh rahi."

    parts: list[str] = []
    top_groups = data.get("top_groups", [])

    for f in findings_list[:2]:
        code = f.get("code", "")
        if code == "RAM_HIGH":
            ram_pct = data.get("ram_used_pct", 0)
            if top_groups:
                g = top_groups[0]
                ram_gb = round(g.get("ram_mb", 0) / 1000.0, 1)
                parts.append(
                    f"RAM {ram_pct}% use ho rahi hai. "
                    f"{g.get('name', '').capitalize()} ke {g.get('procs', 0)} processes "
                    f"{ram_gb} GB le rahe hain."
                )
            else:
                parts.append(f"RAM {ram_pct}% use ho rahi hai.")
        elif code == "CPU_HIGH":
            cpu_pct = data.get("cpu_avg_pct", 0)
            parts.append(f"CPU {cpu_pct}% average hai.")
        elif code == "DISK_LOW":
            disk_pct = data.get("disk_free_pct", 0)
            parts.append(f"Disk mein sirf {disk_pct}% jagah bachi hai.")
        elif code == "STARTUP_HIGH":
            count = data.get("startup_apps", 0)
            parts.append(f"Startup mein {count} apps hain.")

    if not parts:
        return "Laptop theek lag raha hai, koi problem nahi dikh rahi."

    reply = " ".join(parts)
    words = reply.split()
    if len(words) > 40:
        reply = " ".join(words[:40])
    return reply
