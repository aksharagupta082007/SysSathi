"""Battery report — psutil for basics, PowerShell WMI for health."""

from __future__ import annotations

import asyncio
import json
import platform
import subprocess
import sys
from typing import Any


def parse_battery(
    psutil_battery: Any | None,
    ps_static_output: str | None,
    ps_fullcharge_output: str | None,
) -> dict[str, Any]:
    """Build battery report from raw data (pure logic, no subprocess calls).

    psutil_battery: result of psutil.sensors_battery() or None.
    ps_static_output: JSON string from PowerShell BatteryStaticData or None.
    ps_fullcharge_output: JSON string from PowerShell BatteryFullChargedCapacity or None.
    """
    if psutil_battery is None:
        return {"has_battery": False}

    result: dict[str, Any] = {
        "has_battery": True,
        "charge_pct": round(psutil_battery.percent, 1),
        "plugged": psutil_battery.power_plugged or False,
    }

    designed = _parse_capacity(ps_static_output, "DesignedCapacity")
    full_charge = _parse_capacity(ps_fullcharge_output, "FullChargedCapacity")

    if designed is not None and full_charge is not None and designed > 0:
        result["designed_capacity_mwh"] = designed
        result["full_charge_capacity_mwh"] = full_charge
        result["health_pct"] = round((full_charge / designed) * 100, 1)
    else:
        result["health_available"] = False

    return result


def _parse_capacity(ps_output: str | None, key: str) -> int | None:
    """Extract a capacity value from PowerShell JSON output."""
    if not ps_output:
        return None
    try:
        data = json.loads(ps_output)
        # PowerShell may return a list or a single object
        if isinstance(data, list):
            if not data:
                return None
            data = data[0]
        val = data.get(key)
        return int(val) if val is not None else None
    except (json.JSONDecodeError, ValueError, TypeError, AttributeError):
        return None


def _run_ps_command(class_name: str) -> str | None:
    """Run a PowerShell Get-CimInstance command and return JSON output.

    No shell=True. Fixed arguments only.
    """
    cmd = [
        sys.executable.replace("python.exe", "").rstrip("\\").rstrip("/")
        and "powershell.exe",
        "-NoProfile",
        "-NonInteractive",
        "-Command",
        f"Get-CimInstance -Namespace root/wmi -ClassName {class_name} | ConvertTo-Json",
    ]
    # Safer: use the known powershell path
    cmd[0] = "powershell.exe"
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass
    return None


def _get_battery_sync() -> dict[str, Any]:
    """Collect battery data (Windows only)."""
    import psutil

    battery = psutil.sensors_battery()
    if battery is None:
        return parse_battery(None, None, None)

    ps_static = _run_ps_command("BatteryStaticData")
    ps_fullcharge = _run_ps_command("BatteryFullChargedCapacity")
    return parse_battery(battery, ps_static, ps_fullcharge)


async def get_battery_report() -> dict[str, Any]:
    """Get battery report. Returns {"supported": false} on non-Windows."""
    if platform.system() != "Windows":
        return {"supported": False}
    return await asyncio.to_thread(_get_battery_sync)

