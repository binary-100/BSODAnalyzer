"""System Restore, protection settings, Device Manager (extracted from driver_catalog)."""

from __future__ import annotations

import json
import os
import subprocess
import sys


def _dc(name: str):
    import driver_catalog as dc

    return getattr(dc, name)


def get_system_restore_status() -> dict:
    """Whether System Restore is enabled on the system drive (needs admin for full accuracy)."""
    if _dc("run_powershell") is None:
        return {"enabled": None, "drive": "C:", "message": "PowerShell not available."}
    ps = r"""
$drive = $env:SystemDrive
if (-not $drive) { $drive = 'C:' }
$enabled = $null
try {
  $sr = Get-CimInstance -ClassName Win32_SystemRestore -Namespace root\default -EA Stop
  if ($sr) { $enabled = ($sr.DisableStatus -eq 0) }
} catch {}
if ($null -eq $enabled) {
  $key = Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\SystemRestore' -EA 0
  if ($key -and $null -ne $key.DisableSR) { $enabled = ($key.DisableSR -eq 0) }
}
[PSCustomObject]@{ Drive = $drive; Enabled = $enabled } | ConvertTo-Json -Compress
"""
    ok, out = _dc("run_powershell")(ps)
    if ok and out:
        try:
            data = json.loads(out)
            return {
                "enabled": data.get("Enabled"),
                "drive": (data.get("Drive") or "C:").rstrip("\\") + "\\",
                "message": "",
            }
        except json.JSONDecodeError:
            pass
    return {"enabled": None, "drive": "C:\\", "message": out or "Could not read System Restore status."}
def open_system_protection_settings() -> tuple[bool, str]:
    """Open the System Protection / System Restore GUI."""
    if sys.platform != "win32":
        return False, "Only supported on Windows."
    try:
        subprocess.Popen(
            ["SystemPropertiesProtection.exe"],
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        return True, "Opened System Protection settings. Turn on protection for your system drive, then try again."
    except OSError:
        try:
            os.startfile("SystemPropertiesProtection.exe")  # type: ignore[attr-defined]
            return True, "Opened System Protection settings."
        except OSError as e:
            return False, str(e)
def enable_system_restore(drive: str | None = None) -> tuple[bool, str, str | None]:
    """Enable System Restore on a drive (admin). Returns (ok, message, error_code)."""
    if _dc("run_powershell") is None:
        return False, "PowerShell not available.", None
    d = (drive or "C:\\").strip()
    if not d.endswith("\\"):
        d = d.rstrip(":") + ":\\"
    d_ps = d.replace("'", "''")
    ps = rf"""
$ErrorActionPreference = 'Stop'
$drive = '{d_ps}'
Enable-ComputerRestore -Drive $drive
'System Restore enabled on ' + $drive
"""
    ok, out = _dc("run_powershell")(ps, timeout=60)
    if ok:
        return True, out or f"System Restore enabled on {d}.", None
    low = (out or "").lower()
    if "access" in low or "denied" in low or "privilege" in low:
        return False, out or "Administrator rights required.", "denied"
    return False, out or "Could not enable System Restore.", "failed"
def create_system_restore_point(
    description: str = "BSOD Analyzer before driver change",
) -> tuple[bool, str, str | None]:
    """Create a restore point. Third value: None, 'disabled', 'denied', or 'failed'."""
    if _dc("run_powershell") is None:
        return False, "PowerShell not available.", None
    ps = rf"""
$ErrorActionPreference = 'Stop'
$type = [Microsoft.PowerShell.Commands.RestorePointType]::Modify_Settings
Checkpoint-Computer -Description '{description.replace("'", "''")}' -RestorePointType $type
'Restore point created.'
"""
    ok, out = _dc("run_powershell")(ps, timeout=90)
    if ok:
        return True, out or "System restore point created.", None
    low = (out or "").lower()
    if "disabled" in low or "1058" in (out or "") or "turn on system protection" in low:
        return False, "System Restore is disabled on this PC.", "disabled"
    if "access" in low or "denied" in low:
        return False, out or "Administrator rights required.", "denied"
    return False, out or "Could not create restore point.", "failed"
def backup_device_driver(
    device_name: str,
    backup_root: str | None = None,
) -> tuple[bool, str]:
    """Export current driver package via pnputil (needs admin)."""
    import driver_backup as drvbackup

    ok, msg, _record = drvbackup.backup_device_driver(device_name, backup_root)
    return ok, msg
def open_device_manager() -> tuple[bool, str]:
    """Open Windows Device Manager (devmgmt.msc)."""
    if sys.platform != "win32":
        return False, "Device Manager is only available on Windows."
    try:
        os.startfile("devmgmt.msc")  # type: ignore[attr-defined]
        return True, "Opened Device Manager."
    except OSError as e:
        return False, f"Could not open Device Manager: {e}"
