"""Startup apps — read registry Run keys and Startup folders with enabled/disabled tracking."""

from __future__ import annotations

import asyncio
import os
import platform
from pathlib import Path
from typing import Any

from syssathi.mcp_server.sanitize import sanitize


def parse_startup_entries(
    registry_entries: list[tuple[str, str] | tuple[str, str, bool]],
    folder_entries: list[str | tuple[str, bool]],
) -> list[dict[str, Any]]:
    """Build startup list from raw data. Returns name, source, and enabled status.

    Never returns command lines.
    """
    result: list[dict[str, Any]] = []
    for item in registry_entries:
        if len(item) == 3:
            name, source, enabled = item  # type: ignore
        else:
            name, source = item[:2]  # type: ignore
            enabled = True
        result.append({"name": sanitize(name), "source": source, "enabled": enabled})

    for item in folder_entries:
        if isinstance(item, tuple):
            filename, enabled = item
        else:
            filename, enabled = item, True
        stem = Path(filename).stem
        result.append({"name": sanitize(stem), "source": "startup_folder", "enabled": enabled})
    return result


def _read_startup_approved(hive: Any, subkey: str) -> dict[str, bool]:
    """Read enabled/disabled status from StartupApproved keys (S8)."""
    import winreg

    status: dict[str, bool] = {}
    try:
        key = winreg.OpenKey(hive, subkey, 0, winreg.KEY_READ)
    except OSError:
        return status
    try:
        i = 0
        while True:
            try:
                name, data, _type = winreg.EnumValue(key, i)
                # First byte: 0x02 is enabled, 0x03 or other is disabled
                if isinstance(data, (bytes, bytearray)) and len(data) > 0:
                    status[name.lower()] = (data[0] == 2)
                i += 1
            except OSError:
                break
    finally:
        winreg.CloseKey(key)
    return status


def _read_registry_run_key(
    hive: Any,
    subkey: str,
    source_label: str,
    approved_map: dict[str, bool] | None = None,
) -> list[tuple[str, str, bool]]:
    """Read value names from a registry Run key with enabled status."""
    import winreg

    entries: list[tuple[str, str, bool]] = []
    try:
        key = winreg.OpenKey(hive, subkey, 0, winreg.KEY_READ)
    except OSError:
        return entries
    try:
        i = 0
        while True:
            try:
                name, _data, _type = winreg.EnumValue(key, i)
                enabled = True
                if approved_map is not None:
                    enabled = approved_map.get(name.lower(), True)
                entries.append((name, source_label, enabled))
                i += 1
            except OSError:
                break
    finally:
        winreg.CloseKey(key)
    return entries


def _read_startup_folder(folder: Path, approved_map: dict[str, bool] | None = None) -> list[tuple[str, bool]]:
    """List filenames and enabled status in a Startup folder."""
    if not folder.is_dir():
        return []
    res: list[tuple[str, bool]] = []
    for f in folder.iterdir():
        if f.is_file():
            enabled = True
            if approved_map is not None:
                enabled = approved_map.get(f.name.lower(), True)
            res.append((f.name, enabled))
    return res


def _list_startup_sync() -> dict[str, Any]:
    """Collect startup apps from registry/folders on Windows, or autostart folders on Linux."""
    if platform.system() == "Windows":
        import winreg

        # Read StartupApproved keys
        hkcu_approved = _read_startup_approved(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run",
        )
        hklm_approved = _read_startup_approved(
            winreg.HKEY_LOCAL_MACHINE,
            r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run",
        )
        hkcu_folder_approved = _read_startup_approved(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\StartupFolder",
        )

        registry_entries: list[tuple[str, str, bool]] = []

        # HKCU Run
        registry_entries.extend(
            _read_registry_run_key(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                "HKCU_Run",
                hkcu_approved,
            )
        )
        # HKLM Run
        registry_entries.extend(
            _read_registry_run_key(
                winreg.HKEY_LOCAL_MACHINE,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                "HKLM_Run",
                hklm_approved,
            )
        )
        # HKLM WOW6432Node Run (32-bit apps on 64-bit Windows)
        registry_entries.extend(
            _read_registry_run_key(
                winreg.HKEY_LOCAL_MACHINE,
                r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Run",
                "HKLM_WOW64_Run",
                hklm_approved,
            )
        )

        # Startup folders
        folder_entries: list[tuple[str, bool]] = []
        user_startup = Path(os.environ.get("APPDATA", "")) / r"Microsoft\Windows\Start Menu\Programs\Startup"
        common_startup = Path(os.environ.get("PROGRAMDATA", "")) / r"Microsoft\Windows\Start Menu\Programs\Startup"
        folder_entries.extend(_read_startup_folder(user_startup, hkcu_folder_approved))
        folder_entries.extend(_read_startup_folder(common_startup, None))

        entries = parse_startup_entries(registry_entries, folder_entries)
        # Count only enabled startup entries (S8)
        enabled_count = len([e for e in entries if e.get("enabled", True)])
        return {"entries": entries, "count": enabled_count}

    elif platform.system() == "Linux":
        folder_entries_linux: list[tuple[str, bool]] = []
        user_autostart = Path.home() / ".config" / "autostart"
        sys_autostart = Path("/etc/xdg/autostart")

        for folder in (user_autostart, sys_autostart):
            if folder.is_dir():
                for f in folder.iterdir():
                    if f.is_file() and f.suffix == ".desktop":
                        enabled = True
                        try:
                            content = f.read_text(encoding="utf-8", errors="ignore")
                            for line in content.splitlines():
                                line_clean = line.strip().lower()
                                if line_clean in ("hidden=true", "x-gnome-autostart-enabled=false"):
                                    enabled = False
                                    break
                        except Exception:
                            pass
                        stem = f.name[:-8] if f.name.endswith(".desktop") else f.name
                        folder_entries_linux.append((stem, enabled))

        entries = parse_startup_entries([], folder_entries_linux)
        enabled_count = len([e for e in entries if e.get("enabled", True)])
        return {"entries": entries, "count": enabled_count}

    return {"entries": [], "count": 0}


async def list_startup_apps() -> dict[str, Any]:
    """List startup apps. Returns {"supported": false} on unsupported OS."""
    if platform.system() not in ("Windows", "Linux"):
        return {"supported": False}
    return await asyncio.to_thread(_list_startup_sync)
