"""Active network adapter power management (Windows Get/Set-NetAdapterPowerManagement)."""

from __future__ import annotations

import json
import re
import sys
from typing import Any

# MSFT_NetAdapterPowerManagementSettingData.AllowComputerToTurnOffDevice
_ALLOW_UNSUPPORTED = 0
_ALLOW_ENABLED = 1  # Windows may turn off adapter to save power
_ALLOW_DISABLED = 2  # Adapter stays powered — better for long online scans


def _run_ps(script: str, *, timeout: int = 45) -> tuple[bool, str]:
    if sys.platform != "win32":
        return False, "Only supported on Windows."
    try:
        import bsod_runtime as rt

        return rt.run_powershell(script, timeout=timeout)
    except ImportError:
        return False, "PowerShell not available."


def _parse_json_object(raw: str) -> dict[str, Any] | None:
    text = (raw or "").strip()
    if not text:
        return None
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        data = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def query_active_network_adapter() -> dict[str, Any] | None:
    """Return the adapter carrying the default route (or first Up non-virtual adapter)."""
    ps = r"""
$ErrorActionPreference = 'SilentlyContinue'
$up = @(Get-NetAdapter | Where-Object { $_.Status -eq 'Up' -and $_.Virtual -eq $false })
if (-not $up) { return }
$route = Get-NetRoute -AddressFamily IPv4 -DestinationPrefix '0.0.0.0/0' -ErrorAction SilentlyContinue |
  Sort-Object RouteMetric, InterfaceMetric | Select-Object -First 1
$alias = $null
if ($route) { $alias = $route.InterfaceAlias }
$na = $null
if ($alias) { $na = $up | Where-Object { $_.Name -eq $alias } | Select-Object -First 1 }
if (-not $na) { $na = $up | Select-Object -First 1 }
if (-not $na) { return }
$pm = Get-NetAdapterPowerManagement -Name $na.Name -ErrorAction SilentlyContinue
$allow = $null
if ($pm) { $allow = [int]$pm.AllowComputerToTurnOffDevice }
[PSCustomObject]@{
  Name = [string]$na.Name
  InterfaceDescription = [string]$na.InterfaceDescription
  MediaType = [string]$na.MediaType
  Status = [string]$na.Status
  AllowComputerToTurnOffDevice = $allow
  PowerSavingOn = ($allow -eq 1)
  PowerManagementSupported = ($allow -ne 0 -and $null -ne $allow)
} | ConvertTo-Json -Compress
"""
    ok, out = _run_ps(ps)
    if not ok:
        return None
    data = _parse_json_object(out)
    if not data or not (data.get("Name") or "").strip():
        return None
    allow = data.get("AllowComputerToTurnOffDevice")
    try:
        allow_int = int(allow) if allow is not None else _ALLOW_UNSUPPORTED
    except (TypeError, ValueError):
        allow_int = _ALLOW_UNSUPPORTED
    data["AllowComputerToTurnOffDevice"] = allow_int
    data["PowerSavingOn"] = allow_int == _ALLOW_ENABLED
    data["PowerManagementSupported"] = allow_int in (_ALLOW_ENABLED, _ALLOW_DISABLED)
    return data


def set_active_adapter_allow_turn_off(
    adapter_name: str,
    *,
    allow_turn_off: bool,
) -> tuple[bool, str]:
    """Set 'Allow the computer to turn off this device to save power' on one adapter."""
    name = (adapter_name or "").strip()
    if not name:
        return False, "No adapter name."
    if not re.match(r"^[\w\s\-().]+$", name):
        return False, "Invalid adapter name."
    safe = name.replace("'", "''")
    setting = "Enabled" if allow_turn_off else "Disabled"
    ps = f"""
$ErrorActionPreference = 'Stop'
Set-NetAdapterPowerManagement -Name '{safe}' -AllowComputerToTurnOffDevice {setting}
'OK'
"""
    ok, out = _run_ps(ps, timeout=60)
    if ok and "OK" in (out or ""):
        state = "on (adapter may sleep to save power)" if allow_turn_off else "off (adapter stays awake)"
        return True, f"Power saving for '{name}' is now {state}."
    return False, (out or "Could not change adapter power setting.")[:500]


def adapter_power_summary(adapter: dict[str, Any] | None) -> str:
    if not adapter:
        return "No active network adapter detected."
    desc = (adapter.get("InterfaceDescription") or adapter.get("Name") or "?").strip()
    if not adapter.get("PowerManagementSupported"):
        return f"{desc} — power management setting not available on this adapter."
    if adapter.get("PowerSavingOn"):
        return (
            f"{desc} — Windows may turn off this adapter to save power. "
            "Enable “Keep adapter awake” below for more reliable online driver scans."
        )
    return f"{desc} — adapter is set to stay awake (good for driver scans)."
