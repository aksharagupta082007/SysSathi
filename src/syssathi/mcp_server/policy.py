"""Thresholds and protected-process list — single source of truth."""

from __future__ import annotations

import os


# --- Thresholds (overridable by env vars) ---

def _env_float(key: str, default: float) -> float:
    val = os.environ.get(key)
    return float(val) if val else default


def _env_int(key: str, default: int) -> int:
    val = os.environ.get(key)
    return int(val) if val else default


def get_thresholds() -> dict[str, float | int]:
    """Return current thresholds, respecting env overrides."""
    return {
        "RAM_HIGH_PCT": _env_float("SYSSATHI_RAM_HIGH_PCT", 85.0),
        "DISK_LOW_PCT": _env_float("SYSSATHI_DISK_LOW_PCT", 10.0),
        "STARTUP_HIGH_COUNT": _env_int("SYSSATHI_STARTUP_HIGH_COUNT", 8),
        "CPU_HIGH_PCT": _env_float("SYSSATHI_CPU_HIGH_PCT", 80.0),
    }


# --- Protected process names ---

PROTECTED_NAMES: frozenset[str] = frozenset({
    "system",
    "system idle process",
    "registry",
    "smss",
    "csrss",
    "wininit",
    "winlogon",
    "services",
    "lsass",
    "svchost",
    "explorer",
    "dwm",
    "fontdrvhost",
    "msmpeng",
    "securityhealthservice",
    # Development / shell safeguards
    "agy",
    "antigravity",
    "code",
    "bash",
    "wsl",
    "wslhost",
    "init",
})


def normalize_process_name(name: str) -> str:
    """Lowercase and strip trailing .exe."""
    n = name.lower().strip()
    if n.endswith(".exe"):
        n = n[:-4]
    return n


def is_protected(name: str) -> bool:
    """Check if a process name is protected.

    Ignores case and .exe suffix.  Any name containing 'python' is protected.
    """
    normalized = normalize_process_name(name)
    if normalized in PROTECTED_NAMES:
        return True
    if "python" in normalized:
        return True
    return False


def get_protected_pids() -> set[int]:
    """Return PIDs that must never be killed.

    Includes the current process (server), its parent (host),
    and their respective parents.
    """
    pids: set[int] = set()
    try:
        import psutil
        for pid in (os.getpid(), os.getppid()):
            pids.add(pid)
            try:
                parent = psutil.Process(pid).ppid()
                if parent:
                    pids.add(parent)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
    except Exception:
        # Fallback: at minimum protect our own PID and parent
        pids.add(os.getpid())
        try:
            pids.add(os.getppid())
        except OSError:
            pass
    return pids

