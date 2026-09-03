"""
Driver backup, restore, and backup-library management.

Backups are pnputil /export-driver folders with a manifest.json sidecar.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

try:
    from bsod_runtime import run_powershell
except ImportError:
    run_powershell = None  # type: ignore[assignment,misc]

try:
    from product_version import product_version

    APP_VERSION = product_version()
except ImportError:
    APP_VERSION = "0.0.0"

MANIFEST_NAME = "manifest.json"
ProgressCb = Callable[[str], None] | None


def default_backup_root(settings: dict | None = None) -> str:
    """Resolve driver backup folder from settings or default."""
    custom = ""
    if settings:
        custom = (settings.get("driver_backup_folder") or "").strip()
    if custom:
        return os.path.abspath(custom)
    return os.path.join(
        os.environ.get("LOCALAPPDATA", os.path.expanduser("~")),
        "BSODAnalyzer",
        "driver_backups",
    )


def backup_keep_count(settings: dict | None = None) -> int:
    if not settings:
        return 3
    try:
        n = int(settings.get("driver_backup_keep_count", 3))
    except (TypeError, ValueError):
        n = 3
    return max(0, min(n, 99))


def backup_before_install_default(settings: dict | None = None) -> bool:
    if not settings:
        return True
    return bool(settings.get("driver_backup_before_install", True))


def _safe_folder_name(device_name: str) -> str:
    return re.sub(r'[<>:"/\\|?*]', "_", (device_name or "device").strip())[:60] or "device"


def _read_manifest(folder: str) -> dict | None:
    path = os.path.join(folder, MANIFEST_NAME)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def _write_manifest(folder: str, record: dict) -> None:
    path = os.path.join(folder, MANIFEST_NAME)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(record, f, indent=2)


def _query_signed_driver(device_name: str) -> dict:
    if run_powershell is None:
        return {}
    name_esc = (device_name or "").replace("'", "''")
    ps = rf"""
$ErrorActionPreference = 'Stop'
$d = Get-CimInstance Win32_PnPSignedDriver -EA 0 |
  Where-Object {{ $_.DeviceName -eq '{name_esc}' }} |
  Select-Object -First 1 DeviceName, DriverVersion, InfName, DriverDate
if (-not $d) {{ '{{}}' }} else {{
  [PSCustomObject]@{{
    DeviceName = $d.DeviceName
    DriverVersion = $d.DriverVersion
    InfName = $d.InfName
    DriverDate = if ($d.DriverDate) {{ $d.DriverDate.ToString('yyyy-MM-dd') }} else {{ '' }}
  }} | ConvertTo-Json -Compress
}}
"""
    ok, out = run_powershell(ps, timeout=60)
    if not ok or not out.strip():
        return {}
    try:
        data = json.loads(out.strip())
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def backup_device_driver(
    device_name: str,
    backup_root: str | None = None,
    *,
    progress_cb: ProgressCb = None,
) -> tuple[bool, str, dict | None]:
    """Export current driver via pnputil; write manifest.json in backup folder."""
    if run_powershell is None:
        return False, "PowerShell not available.", None
    device_name = (device_name or "").strip()
    if not device_name:
        return False, "No device name for driver backup.", None

    if progress_cb:
        progress_cb("Reading installed driver info…")
    drv = _query_signed_driver(device_name)
    inf = (drv.get("InfName") or "").strip()
    if not inf:
        return (
            False,
            f"No signed driver INF found for “{device_name}”. "
            "Try Device Manager or pick another device.",
            None,
        )

    root = backup_root or default_backup_root()
    os.makedirs(root, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = os.path.join(root, _safe_folder_name(device_name), stamp)
    os.makedirs(dest, exist_ok=True)

    if progress_cb:
        progress_cb("Exporting driver package…")
    dest_esc = dest.replace("'", "''")
    inf_esc = inf.replace("'", "''")
    ps = rf"""
$ErrorActionPreference = 'Stop'
$out = & pnputil /export-driver '{inf_esc}' '{dest_esc}' 2>&1 | Out-String
if ($LASTEXITCODE -ne 0) {{ throw $out }}
$out
"""
    ok, out = run_powershell(ps, timeout=300)
    if not ok:
        shutil.rmtree(dest, ignore_errors=True)
        return False, out or "Driver backup failed (try running as Administrator).", None

    backed_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    record = {
        "device_name": device_name,
        "driver_version": (drv.get("DriverVersion") or "").strip(),
        "driver_date": (drv.get("DriverDate") or "").strip(),
        "inf_name": inf,
        "backed_up_at": backed_at,
        "backed_up_at_local": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "app_version": APP_VERSION,
        "path": dest,
    }
    _write_manifest(dest, record)
    msg = (
        f"Backed up driver for:\n{device_name}\n\n"
        f"Version: {record['driver_version'] or '?'}\n"
        f"Saved to:\n{dest}"
    )
    return True, msg, record


def restore_driver_backup(
    backup_path: str,
    *,
    progress_cb: ProgressCb = None,
) -> tuple[bool, str]:
    """Reinstall a backed-up driver folder via pnputil."""
    if run_powershell is None:
        return False, "PowerShell not available."
    folder = os.path.abspath((backup_path or "").strip())
    if not os.path.isdir(folder):
        return False, f"Backup folder not found:\n{folder}"

    if progress_cb:
        progress_cb("Restoring backed-up driver…")
    folder_esc = folder.replace("'", "''")
    ps = rf"""
$ErrorActionPreference = 'Stop'
$out = & pnputil /add-driver '{folder_esc}' /subdirs /install 2>&1 | Out-String
if ($LASTEXITCODE -ne 0) {{ throw $out }}
$out
"""
    ok, out = run_powershell(ps, timeout=300)
    if ok:
        manifest = _read_manifest(folder) or {}
        device = manifest.get("device_name") or "device"
        return True, (out or f"Restored driver backup for {device}.").strip()
    return False, out or "Restore failed (try running as Administrator)."


def list_driver_backups(backup_root: str | None = None) -> list[dict]:
    """Return backup records newest-first."""
    root = backup_root or default_backup_root()
    if not os.path.isdir(root):
        return []
    records: list[dict] = []
    for device_dir in Path(root).iterdir():
        if not device_dir.is_dir():
            continue
        for stamp_dir in device_dir.iterdir():
            if not stamp_dir.is_dir():
                continue
            folder = str(stamp_dir)
            manifest = _read_manifest(folder)
            if manifest:
                rec = dict(manifest)
                rec["path"] = folder
            else:
                rec = {
                    "device_name": device_dir.name.replace("_", " "),
                    "driver_version": "",
                    "driver_date": "",
                    "backed_up_at": "",
                    "backed_up_at_local": stamp_dir.name,
                    "path": folder,
                }
            records.append(rec)

    def _sort_key(r: dict) -> str:
        return (r.get("backed_up_at") or r.get("backed_up_at_local") or r.get("path") or "")

    records.sort(key=_sort_key, reverse=True)
    return records


def remove_driver_backup(backup_path: str) -> tuple[bool, str]:
    folder = os.path.abspath((backup_path or "").strip())
    if not os.path.isdir(folder):
        return False, "Backup folder not found."
    try:
        shutil.rmtree(folder)
    except OSError as exc:
        return False, str(exc)
    parent = os.path.dirname(folder)
    try:
        if os.path.isdir(parent) and not os.listdir(parent):
            os.rmdir(parent)
    except OSError:
        pass
    return True, f"Removed backup:\n{folder}"


def export_backup_zip(backup_path: str, zip_path: str) -> tuple[bool, str]:
    folder = os.path.abspath((backup_path or "").strip())
    if not os.path.isdir(folder):
        return False, "Backup folder not found."
    dest = os.path.abspath((zip_path or "").strip())
    if not dest.lower().endswith(".zip"):
        dest += ".zip"
    try:
        os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
        with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
            for dirpath, _dirs, files in os.walk(folder):
                for name in files:
                    full = os.path.join(dirpath, name)
                    arc = os.path.relpath(full, os.path.dirname(folder))
                    zf.write(full, arc)
    except OSError as exc:
        return False, str(exc)
    return True, f"Exported backup zip:\n{dest}"


def prune_driver_backups(
    backup_root: str | None = None,
    *,
    keep_per_device: int = 3,
) -> tuple[int, str]:
    """Keep newest N backups per device folder; return (removed_count, message)."""
    if keep_per_device <= 0:
        return 0, "Auto-prune disabled (keep count is 0)."
    root = backup_root or default_backup_root()
    if not os.path.isdir(root):
        return 0, "No backup folder."
    removed = 0
    for device_dir in Path(root).iterdir():
        if not device_dir.is_dir():
            continue
        subs = sorted(
            (p for p in device_dir.iterdir() if p.is_dir()),
            key=lambda p: p.name,
            reverse=True,
        )
        for old in subs[keep_per_device:]:
            ok, _msg = remove_driver_backup(str(old))
            if ok:
                removed += 1
    if removed:
        return removed, f"Removed {removed} old backup(s); kept {keep_per_device} per device."
    return 0, ""
