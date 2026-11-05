"""Startup apps — read registry Run keys and Startup folders."""

from __future__ import annotations

import asyncio
import os
import platform
from pathlib import Path
from typing import Any

from syssathi.mcp_server.sanitize import sanitize


def parse_startup_entries(
    registry_entries: list[tuple[str, str]],
    folder_entries: list[str],
) -> list[dict[str, str]]:
    """Build startup list from raw data. Returns name and source only.

    registry_entries: list of (name, source_key) from winreg.
    folder_entries: list of filenames from Startup folders.
    Never returns command lines.
    """
    result: list[dict[str, str]] = []
    for name, source in registry_entries:
        result.append({"name": sanitize(name), "source": source})
    for filename in folder_entries:
        # Strip extension for display
        stem = Path(filename).stem
        result.append({"name": sanitize(stem), "source": "startup_folder"})
    return result


def _read_registry_run_key(hive: Any, subkey: str, source_label: str) -> list[tuple[str, str]]:
    """Read value names from a registry Run key. Returns (name, source_label) pairs."""
    import winreg

    entries: list[tuple[str, str]] = []
    try:
        key = winreg.OpenKey(hive, subkey, 0, winreg.KEY_READ)
    except OSError:
        return entries
    try:
        i = 0
        while True:
            try:
                name, _data, _type = winreg.EnumValue(key, i)
                entries.append((name, source_label))
                i += 1
            except OSError:
                break
    finally:
        winreg.CloseKey(key)
    return entries


def _read_startup_folder(folder: Path) -> list[str]:
    """List filenames in a Startup folder."""
    if not folder.is_dir():
        return []
    return [f.name for f in folder.iterdir() if f.is_file()]


def _list_startup_sync() -> dict[str, Any]:
    """Collect startup apps from registry and folders (Windows only)."""
    import winreg

    registry_entries: list[tuple[str, str]] = []

    # HKCU Run
    registry_entries.extend(
        _read_registry_run_key(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            "HKCU_Run",
        )
    )
    # HKLM Run
    registry_entries.extend(
        _read_registry_run_key(
            winreg.HKEY_LOCAL_MACHINE,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            "HKLM_Run",
        )
    )

    # Startup folders
    folder_entries: list[str] = []
    user_startup = Path(os.environ.get("APPDATA", "")) / r"Microsoft\Windows\Start Menu\Programs\Startup"
    common_startup = Path(os.environ.get("PROGRAMDATA", "")) / r"Microsoft\Windows\Start Menu\Programs\Startup"
    folder_entries.extend(_read_startup_folder(user_startup))
    folder_entries.extend(_read_startup_folder(common_startup))

    entries = parse_startup_entries(registry_entries, folder_entries)
    return {"entries": entries, "count": len(entries)}


async def list_startup_apps() -> dict[str, Any]:
    """List startup apps. Returns {"supported": false} on non-Windows."""
    if platform.system() != "Windows":
        return {"supported": False}
    return await asyncio.to_thread(_list_startup_sync)

