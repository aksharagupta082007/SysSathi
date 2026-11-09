"""WSL detection and host environment validation (Decision 1 & §7)."""

from __future__ import annotations

import os
import platform
import sys
from pathlib import Path
from typing import Any


def is_wsl() -> bool:
    """Return True if running inside Windows Subsystem for Linux (WSL)."""
    if platform.system() != "Linux":
        return False

    if os.environ.get("WSL_DISTRO_NAME") or os.environ.get("WSL_INTEROP"):
        return True

    proc_version = Path("/proc/version")
    if proc_version.exists():
        try:
            content = proc_version.read_text(encoding="utf-8", errors="ignore").lower()
            return "microsoft" in content or "wsl" in content
        except Exception:
            pass

    return False


def get_environment_info() -> dict[str, Any]:
    """Return runtime host environment details with WSL warning if applicable."""
    system_os = platform.system()
    in_wsl = is_wsl()

    warning: str | None = None
    if in_wsl:
        warning = (
            "Running inside WSL (Linux VM). Diagnostic tools, battery, startup apps, and process actions "
            "apply to the WSL virtual machine, NOT your native Windows laptop. For accurate laptop inspection, "
            "run natively in Windows PowerShell with Python 3.12."
        )

    return {
        "os": system_os,
        "is_wsl": in_wsl,
        "python_version": sys.version.split()[0],
        "warning": warning,
    }

