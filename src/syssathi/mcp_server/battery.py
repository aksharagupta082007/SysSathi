"""Battery report — psutil for basics, PowerShell WMI / powercfg for health."""

from __future__ import annotations

import asyncio
import json
import os
import platform
import subprocess
from pathlib import Path
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
        result["unit"] = "mWh"
    else:
        result["health_available"] = False

    return result


def _parse_capacity(ps_output: str | None, key: str) -> int | None:
    """Extract a capacity value from PowerShell JSON output."""
    if not ps_output:
        return None
    try:
        data = json.loads(ps_output)
        if isinstance(data, list):
            if not data:
                return None
            data = data[0]
        val = data.get(key)
        return int(val) if val is not None else None
    except (json.JSONDecodeError, ValueError, TypeError, AttributeError):
        return None


def _run_ps_command(class_name: str) -> str | None:
    """Run a PowerShell Get-CimInstance command and return JSON output."""
    cmd = [
        "powershell.exe",
        "-NoProfile",
        "-NonInteractive",
        "-Command",
        f"Get-CimInstance -Namespace root/wmi -ClassName {class_name} | ConvertTo-Json",
    ]
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


def _get_battery_from_powercfg() -> tuple[int | None, int | None]:
    """Fallback on Windows: generate XML battery report via powercfg.exe."""
    import tempfile
    import xml.etree.ElementTree as ET

    with tempfile.NamedTemporaryFile(suffix=".xml", delete=False) as tf:
        tmp_path = tf.name

    try:
        cmd = ["powercfg.exe", "/batteryreport", "/xml", "/output", tmp_path]
        res = subprocess.run(
            cmd,
            capture_output=True,
            timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
        )
        if res.returncode == 0 and os.path.exists(tmp_path):
            tree = ET.parse(tmp_path)
            root = tree.getroot()
            design_elem = root.find(".//{*}DesignCapacity") or root.find(".//DesignCapacity")
            full_elem = root.find(".//{*}FullChargeCapacity") or root.find(".//FullChargeCapacity")
            design_val = int(design_elem.text.strip()) if design_elem is not None and design_elem.text else None
            full_val = int(full_elem.text.strip()) if full_elem is not None and full_elem.text else None
            return design_val, full_val
    except Exception:
        pass
    finally:
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except OSError:
            pass
    return None, None


def _get_linux_battery_capacities() -> tuple[str | None, str | None]:
    """Read full charge and design capacities from /sys/class/power_supply/ on Linux."""
    ps_path = Path("/sys/class/power_supply")
    if not ps_path.exists():
        return None, None
    for bat in ps_path.glob("BAT*"):
        designed: int | None = None
        full: int | None = None
        for design_key in ("energy_full_design", "charge_full_design"):
            p = bat / design_key
            if p.exists():
                try:
                    raw = int(p.read_text().strip())
                    # If energy in µWh, convert to mWh
                    designed = raw // 1000 if "energy" in design_key else raw
                    break
                except (ValueError, OSError):
                    pass
        for full_key in ("energy_full", "charge_full"):
            p = bat / full_key
            if p.exists():
                try:
                    raw = int(p.read_text().strip())
                    full = raw // 1000 if "energy" in full_key else raw
                    break
                except (ValueError, OSError):
                    pass
        if designed and full:
            return json.dumps({"DesignedCapacity": designed}), json.dumps({"FullChargedCapacity": full})
    return None, None


def _get_battery_sync() -> dict[str, Any]:
    """Collect battery data (Windows and Linux)."""
    import psutil

    battery = psutil.sensors_battery()
    if battery is None:
        return parse_battery(None, None, None)

    if platform.system() == "Windows":
        ps_static = _run_ps_command("BatteryStaticData")
        ps_fullcharge = _run_ps_command("BatteryFullChargedCapacity")
        parsed = parse_battery(battery, ps_static, ps_fullcharge)
        if not parsed.get("health_available", True):
            # Fall back to powercfg (S7)
            d_cap, f_cap = _get_battery_from_powercfg()
            if d_cap and f_cap and d_cap > 0:
                parsed["designed_capacity_mwh"] = d_cap
                parsed["full_charge_capacity_mwh"] = f_cap
                parsed["health_pct"] = round((f_cap / d_cap) * 100, 1)
                parsed["unit"] = "mWh"
                parsed.pop("health_available", None)
        return parsed
    elif platform.system() == "Linux":
        ps_static, ps_fullcharge = _get_linux_battery_capacities()
        return parse_battery(battery, ps_static, ps_fullcharge)

    return parse_battery(battery, None, None)


async def get_battery_report() -> dict[str, Any]:
    """Get battery report. Returns {"supported": false} on unsupported OS."""
    if platform.system() not in ("Windows", "Linux", "Darwin"):
        return {"supported": False}
    return await asyncio.to_thread(_get_battery_sync)
