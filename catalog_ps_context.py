"""PowerShell context probe and PnPSignedDriver index (extracted from driver_catalog)."""

from __future__ import annotations

import json
import threading
import time

import catalog_mscatalog_session as _mscat_sess
from catalog_mscatalog_session import _cap_session_rows


def _dc(name: str):
    import driver_catalog as dc

    return getattr(dc, name)


_CATALOG_CACHE_LOCK = threading.Lock()
_POWERSHELL_CATALOG_DEGRADED: bool = False


def _run_catalog_ps(script: str, timeout: int = 30) -> tuple[bool, str]:
    """Catalog/WMI PowerShell — globally serialized to keep the GUI stable."""
    run_catalog_powershell = _dc("run_catalog_powershell")
    run_powershell = _dc("run_powershell")
    if run_catalog_powershell is not None:
        return run_catalog_powershell(script, timeout=timeout)
    if run_powershell is not None:
        return run_powershell(script, timeout=timeout)
    return False, "PowerShell unavailable"


def catalog_powershell_available() -> bool:
    return _dc("run_powershell") is not None


def mark_catalog_powershell_degraded() -> None:
    global _POWERSHELL_CATALOG_DEGRADED
    _POWERSHELL_CATALOG_DEGRADED = True


def consume_catalog_powershell_degraded() -> bool:
    global _POWERSHELL_CATALOG_DEGRADED
    was = _POWERSHELL_CATALOG_DEGRADED
    _POWERSHELL_CATALOG_DEGRADED = False
    return was


def _get_pnpsigned_driver_rows() -> list[dict]:
    """Cached Win32_PnPSignedDriver rows for installed version fallback."""
    now = time.monotonic()
    if (
        _mscat_sess._PNPSIGNED_DRIVER_CACHE is not None
        and (now - _mscat_sess._PNPSIGNED_DRIVER_CACHE_AT)
        < _mscat_sess._PNPSIGNED_DRIVER_CACHE_TTL_SEC
    ):
        return _mscat_sess._PNPSIGNED_DRIVER_CACHE
    if _dc("run_powershell") is None and _dc("run_catalog_powershell") is None:
        mark_catalog_powershell_degraded()
        return []
    with _CATALOG_CACHE_LOCK:
        if (
            _mscat_sess._PNPSIGNED_DRIVER_CACHE is not None
            and (now - _mscat_sess._PNPSIGNED_DRIVER_CACHE_AT)
            < _mscat_sess._PNPSIGNED_DRIVER_CACHE_TTL_SEC
        ):
            return _mscat_sess._PNPSIGNED_DRIVER_CACHE
    ps = r"""
$ErrorActionPreference = 'SilentlyContinue'
Get-CimInstance Win32_PnPSignedDriver -EA 0 |
  Select-Object DeviceName, DriverVersion, Manufacturer |
  ConvertTo-Json -Compress
"""
    ok, out = _run_catalog_ps(ps, timeout=90)
    rows: list[dict] = []
    if ok and out and out.strip():
        try:
            data = json.loads(out)
            if isinstance(data, dict):
                data = [data]
            rows = [r for r in data if isinstance(r, dict)]
        except json.JSONDecodeError:
            rows = []
    rows = _cap_session_rows(rows)
    with _CATALOG_CACHE_LOCK:
        _mscat_sess._PNPSIGNED_DRIVER_CACHE = rows
        _mscat_sess._PNPSIGNED_DRIVER_CACHE_AT = time.monotonic()
    return rows


def _build_pnpsigned_version_index() -> dict[str, str]:
    """Device display name (lower) -> driver version; built once per batch/session."""
    index: dict[str, str] = {}
    for row in _get_pnpsigned_driver_rows():
        dn = (row.get("DeviceName") or "").strip()
        ver = (row.get("DriverVersion") or "").strip()
        if dn and ver:
            index[dn.lower()] = ver
    return index


def extend_system_ctx_for_catalog(system_ctx: dict | None) -> dict:
    """Add service tag, machine type, baseboard, and video controllers for OEM/vendor APIs."""
    ctx = dict(system_ctx or {})
    if (
        ctx.get("video_controllers")
        and ctx.get("service_tag")
        and ctx.get("baseboard_product")
        and ctx.get("system_model")
        and ctx.get("system_sku")
    ):
        return ctx
    if _dc("run_powershell") is None and _dc("run_catalog_powershell") is None:
        return ctx
    with _CATALOG_CACHE_LOCK:
        if (
            ctx.get("video_controllers")
            and ctx.get("service_tag")
            and ctx.get("baseboard_product")
            and ctx.get("system_model")
        ):
            return ctx
    ps = r"""
$bios = Get-CimInstance Win32_BIOS -EA 0 | Select-Object -First 1 SerialNumber
$bb = Get-CimInstance Win32_BaseBoard -EA 0 | Select-Object -First 1 Product, Manufacturer
$cs = Get-CimInstance Win32_ComputerSystem -EA 0 | Select-Object -First 1 Model, Manufacturer, SystemSKUNumber
$vc = Get-CimInstance Win32_VideoController -EA 0 | Select-Object Name, PNPDeviceID, DriverVersion, DriverDate
[PSCustomObject]@{
  ServiceTag = ($bios.SerialNumber -as [string]).Trim()
  BaseboardProduct = ($bb.Product -as [string]).Trim()
  BaseboardManufacturer = ($bb.Manufacturer -as [string]).Trim()
  SystemModel = ($cs.Model -as [string]).Trim()
  SystemManufacturer = ($cs.Manufacturer -as [string]).Trim()
  SystemSku = ($cs.SystemSKUNumber -as [string]).Trim()
  MachineType = ($bb.Product -as [string]).Trim()
  VideoControllers = @($vc | ForEach-Object {
    [PSCustomObject]@{
      name = $_.Name
      pnp_device_id = $_.PNPDeviceID
      driver_version = $_.DriverVersion
      driver_date = if ($_.DriverDate) { $_.DriverDate.ToString('yyyy-MM-dd') } else { '' }
    }
  })
} | ConvertTo-Json -Compress -Depth 4
"""
    ok, out = _run_catalog_ps(ps)
    if ok and out:
        try:
            data = json.loads(out)
            if not ctx.get("service_tag"):
                ctx["service_tag"] = (data.get("ServiceTag") or "").strip()
            if not ctx.get("baseboard_product"):
                ctx["baseboard_product"] = (data.get("BaseboardProduct") or "").strip()
            if not ctx.get("baseboard_manufacturer"):
                ctx["baseboard_manufacturer"] = (
                    data.get("BaseboardManufacturer") or ""
                ).strip()
            if not ctx.get("system_model"):
                ctx["system_model"] = (data.get("SystemModel") or "").strip()
            if not ctx.get("system_manufacturer"):
                ctx["system_manufacturer"] = (
                    data.get("SystemManufacturer") or ""
                ).strip()
            if not ctx.get("system_sku"):
                ctx["system_sku"] = (data.get("SystemSku") or "").strip()
            if not ctx.get("machine_type"):
                ctx["machine_type"] = (data.get("MachineType") or "").strip()
            if not ctx.get("video_controllers"):
                vcs = data.get("VideoControllers") or []
                if isinstance(vcs, dict):
                    vcs = [vcs]
                ctx["video_controllers"] = [
                    {
                        "name": v.get("name"),
                        "pnp_device_id": v.get("pnp_device_id"),
                        "driver_version": v.get("driver_version"),
                        "driver_date": v.get("driver_date"),
                    }
                    for v in vcs
                ]
        except json.JSONDecodeError:
            pass
    return ctx
