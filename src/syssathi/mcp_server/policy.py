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
    # Core Windows OS and session infrastructure
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
    "sihost",
    "ctfmon",
    "audiodg",
    "spoolsv",
    # Windows Defender and Security
    "msmpeng",
    "securityhealthservice",
    "securityhealthhost",
    "smartscreen",
    # Windows Shell & Task Management
    "taskmgr",
    "searchhost",
    "startmenuexperiencehost",
    "shellexperiencehost",
    "lockapp",
    "logonui",
    "textinputhost",
    "applicationframehost",
    # Terminals, Consoles & Shells
    "conhost",
    "cmd",
    "powershell",
    "pwsh",
    "windowsterminal",
    "wt",
    "bash",
    "zsh",
    "sh",
    "fish",
    "dash",
    "tmux",
    "screen",
    # Linux / WSL Core & Init
    "init",
    "systemd",
    "systemd-journald",
    "systemd-udevd",
    "systemd-logind",
    "systemd-resolved",
    "dbus-daemon",
    "dbus-broker",
    "cron",
    "crond",
    "sshd",
    "rsyslogd",
    "udevd",
    "wsl",
    "wslhost",
    "wslservice",
    "wslrelay",
    "gvfsd",
    # Linux Desktop Display & Audio
    "xorg",
    "wayland",
    "weston",
    "gnome-shell",
    "kwin",
    "mutter",
    "xfwm4",
    "pulseaudio",
    "pipewire",
    "wireplumber",
    # Developer Tooling, Editors & Environments
    "agy",
    "antigravity",
    "code",
    "cursor",
    "windsurf",
    "zed",
    "sublime_text",
    "subl",
    "idea64",
    "pycharm64",
    "clion64",
    "webstorm64",
    "devenv",
    "vim",
    "nvim",
    "nano",
    "emacs",
    "docker",
    "dockerd",
    "containerd",
    "podman",
})


def normalize_process_name(name: str) -> str:
    """Lowercase and strip trailing .exe."""
    n = name.lower().strip()
    if n.endswith(".exe"):
        n = n[:-4]
    return n


def get_extra_protected() -> set[str]:
    """Return extra protected names configured via SYSSATHI_EXTRA_PROTECTED env var."""
    raw = os.environ.get("SYSSATHI_EXTRA_PROTECTED", "")
    if not raw:
        return set()
    return {normalize_process_name(x) for x in raw.split(",") if x.strip()}


def is_protected(name: str) -> bool:
    """Check if a process name is protected.

    Ignores case and .exe suffix. Any name containing 'python' is protected.
    Also honors user-provided SYSSATHI_EXTRA_PROTECTED list.
    """
    normalized = normalize_process_name(name)
    if normalized in PROTECTED_NAMES:
        return True
    if "python" in normalized:
        return True
    if normalized in get_extra_protected():
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

