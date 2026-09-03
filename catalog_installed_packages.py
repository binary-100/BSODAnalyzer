"""Add/Remove Programs version cache for chipset suites and vendor packages."""

from __future__ import annotations

import json
import re

from catalog_scoring import (
    _looks_like_amd_adrenalin_version,
    _looks_like_amd_chipset_package_version,
    _looks_like_nvidia_branch_version,
)

try:
    from bsod_runtime import run_powershell
except ImportError:
    run_powershell = None  # type: ignore[assignment,misc]

_INSTALLED_PACKAGE_VERSIONS_CACHE: dict[str, str] | None = None


def clear_installed_package_versions_cache() -> None:
    """Drop Add/Remove Programs version cache (chipset, NVIDIA branch, Adrenalin, …)."""
    global _INSTALLED_PACKAGE_VERSIONS_CACHE
    _INSTALLED_PACKAGE_VERSIONS_CACHE = None


def _register_installed_package_from_name(out: dict[str, str], name: str, ver: str) -> None:
    nl = (name or "").lower().strip()
    if not nl or not ver:
        return
    if re.search(r"amd.*chipset|chipset.*amd|amd_chipset", nl, re.I):
        out["amd_chipset"] = ver
    elif (
        re.search(r"amd", nl, re.I)
        and _looks_like_amd_chipset_package_version(ver)
        and not _looks_like_amd_adrenalin_version(ver)
    ):
        # Some installs list the suite as "AMD Software" without "chipset" in the name.
        out["amd_chipset"] = ver
    elif nl == "amd software" or (
        nl.startswith("amd software")
        and "chipset" not in nl
        and _looks_like_amd_adrenalin_version(ver)
    ):
        out["amd_adrenalin"] = ver
    elif re.search(r"intel.*chipset|chipset.*intel", nl, re.I):
        out["intel_chipset"] = ver
    elif re.search(
        r"intel.*(management engine components|me software|management engine\s+\d)",
        nl,
        re.I,
    ) or (re.search(r"intel.*management engine", nl, re.I) and "interface" not in nl):
        out["intel_me"] = ver
    elif re.search(
        r"intel.*(proset/wireless|wireless bluetooth|connectivity performance|wireless wifi|wi-fi driver)",
        nl,
        re.I,
    ):
        out["intel_wireless"] = ver
    elif re.search(r"killer (performance|intelligence|control|wifi)", nl, re.I):
        out["killer_suite"] = ver
    elif re.search(r"broadcom.*(netxtreme|ethernet|nic)", nl, re.I):
        out["broadcom_ethernet"] = ver
    elif re.search(r"qualcomm.*(atheros|wifi|wireless|bluetooth)", nl, re.I):
        out["qualcomm_wireless"] = ver
    elif re.search(
        r"realtek.*(ethernet|pcie gbe|gaming.*gbe|2\.5gbe|network)",
        nl,
        re.I,
    ):
        out["realtek_ethernet"] = ver
    elif re.search(
        r"nvidia\s+(graphics\s+driver|geforce\s+game\s+ready|display\s+driver)",
        nl,
        re.I,
    ):
        if _looks_like_nvidia_branch_version(ver):
            out["nvidia_branch"] = ver


def _load_installed_package_versions_winreg() -> dict[str, str]:
    """Read chipset suite versions from Add/Remove Programs registry (no PowerShell)."""
    try:
        import winreg
    except ImportError:
        return {}
    out: dict[str, str] = {}
    roots = (
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
    )
    for hive, subkey in roots:
        try:
            with winreg.OpenKey(hive, subkey) as parent:
                count = winreg.QueryInfoKey(parent)[0]
                for i in range(count):
                    try:
                        with winreg.OpenKey(parent, winreg.EnumKey(parent, i)) as sk:
                            name = str(winreg.QueryValueEx(sk, "DisplayName")[0] or "").strip()
                            ver = str(winreg.QueryValueEx(sk, "DisplayVersion")[0] or "").strip()
                    except OSError:
                        continue
                    if not name or not ver:
                        continue
                    _register_installed_package_from_name(out, name, ver)
        except OSError:
            continue
    return out


def _load_installed_package_versions() -> dict[str, str]:
    """Installed WHQL package versions from Add/Remove Programs (chipset suites, etc.)."""
    global _INSTALLED_PACKAGE_VERSIONS_CACHE
    if _INSTALLED_PACKAGE_VERSIONS_CACHE is not None:
        return _INSTALLED_PACKAGE_VERSIONS_CACHE
    out: dict[str, str] = _load_installed_package_versions_winreg()
    if run_powershell is None:
        _INSTALLED_PACKAGE_VERSIONS_CACHE = out
        return out
    ps = r"""
$ErrorActionPreference = 'SilentlyContinue'
$keys = @(
  'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*',
  'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*'
)
Get-ItemProperty $keys -EA 0 |
  Where-Object { $_.DisplayName -and $_.DisplayVersion } |
  Select-Object DisplayName, DisplayVersion |
  ConvertTo-Json -Compress
"""
    ok, raw = run_powershell(ps, timeout=45)
    if ok and raw and raw.strip():
        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                data = [data]
            for row in data:
                if not isinstance(row, dict):
                    continue
                name = (row.get("DisplayName") or "").strip()
                ver = (row.get("DisplayVersion") or "").strip()
                if not name or not ver:
                    continue
                _register_installed_package_from_name(out, name, ver)
        except json.JSONDecodeError:
            pass
    _INSTALLED_PACKAGE_VERSIONS_CACHE = out
    return out


__all__ = [
    "clear_installed_package_versions_cache",
    "_load_installed_package_versions",
    "_load_installed_package_versions_winreg",
    "_register_installed_package_from_name",
]
