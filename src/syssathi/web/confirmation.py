"""Confirmation message templates for re-measure speech after process action."""

from __future__ import annotations

from typing import Any

from syssathi.host.orchestrator import apply_reply_guard


def format_remeasure_reply(
    execution_result: dict[str, Any],
    before_findings: dict[str, Any] | None,
) -> str:
    """Format short Hinglish confirmation speech comparing before and after values.
    
    Uses fixed deterministic templates to guarantee number accuracy with no hallucination.
    Reuses reply guard (<=40 words).
    """
    if "error" in execution_result or execution_result.get("refused"):
        reason = execution_result.get("reason") or execution_result.get("error") or "Proposal invalid hai"
        if "expired" in str(reason).lower():
            text = "Proposal expire ho gaya hai. Dobara check karein."
        elif "used" in str(reason).lower():
            text = "Ye action pehle hi execute ho chuka hai."
        else:
            text = f"Action execute nahi ho paya: {reason}."
        return apply_reply_guard(text)

    closed = execution_result.get("closed_count", execution_result.get("closed", 0))
    skipped = execution_result.get("skipped_count", execution_result.get("skipped", 0))
    failed = execution_result.get("failed_count", execution_result.get("failed", 0))

    # After diagnosis
    after_diag = execution_result.get("fresh_diagnosis") or execution_result.get("diagnosis", {})
    before_ram = before_findings.get("ram_used_pct") if before_findings else None
    after_ram = after_diag.get("ram_used_pct") if isinstance(after_diag, dict) else None

    # Handle process execution details
    parts: list[str] = []
    if closed > 0:
        if before_ram is not None and after_ram is not None:
            if after_ram < before_ram:
                parts.append(f"RAM {round(before_ram):.0f}% se {round(after_ram):.0f}% ho gaya.")
            else:
                parts.append(f"Processes band ho gaye, par RAM {round(after_ram):.0f}% hi rahi.")
        else:
            parts.append(f"{closed} processes band ho gaye.")
    else:
        parts.append("Koi process band nahi ho paya.")

    if skipped > 0:
        parts.append(f"{skipped} processes skip hue.")
    if failed > 0:
        parts.append(f"{failed} processes close hone me fail hue.")

    full_text = " ".join(parts)
    return apply_reply_guard(full_text)

