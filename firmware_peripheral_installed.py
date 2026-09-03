"""Installed peripheral firmware — PnP properties, vendor app caches, user-confirmed versions."""

from __future__ import annotations

import base64
import json
import os
import re
from pathlib import Path
from typing import Any

_USB_VID_PID_RE = re.compile(r"VID[_&]([0-9A-F]{4}).*?PID[_&]([0-9A-F]{4})", re.I)
_FW_VER_IN_TEXT = re.compile(
    r"(?:firmware[_\s-]*version|fw[_\s-]*version|device[_\s-]*firmware)"
    r"[\s:\"'=]*([0-9][0-9A-Za-z._-]{1,24})",
    re.I,
)

# Read-only scan roots (Phase B) — structured JSON only; never scrape .log files.
_VENDOR_JSON_ROOTS: dict[str, tuple[str, ...]] = {
    "razer": (
        "Razer/Synapse3",
        "Razer/RazerAppEngine/User Data/Default",
    ),
    "corsair": ("Corsair",),
    "steelseries": ("SteelSeries",),
    "hyperx": ("HyperX", "NGENUITY"),
}

_LGHUB_DB = "LGHUB/settings.db"
_LGHUB_FW_KEYS = frozenset({
    "firmwareversion",
    "firmware_version",
    "fwversion",
    "devicefirmwareversion",
})


def _local_appdata() -> Path:
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return Path(base)


def device_cache_key(device_id: str) -> str:
    vid, pid = usb_vid_pid(device_id)
    if vid and pid:
        return f"{vid}:{pid}".lower()
    return (device_id or "").strip().upper()[:120]


def usb_vid_pid(device_id: str) -> tuple[str, str]:
    m = _USB_VID_PID_RE.search(device_id or "")
    if not m:
        return "", ""
    return m.group(1).upper(), m.group(2).upper()


def user_confirmed_path() -> Path:
    try:
        import app_settings as apps

        return apps.full_install_data_dir() / "firmware_user_confirmed.json"
    except ImportError:
        return _local_appdata() / "BSODAnalyzer" / "firmware_user_confirmed.json"


def load_user_confirmed() -> dict[str, str]:
    path = user_confirmed_path()
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(k): str(v) for k, v in data.items() if v}


def save_user_confirmed(device_id: str, version: str) -> bool:
    key = device_cache_key(device_id)
    if not key or not (version or "").strip():
        return False
    path = user_confirmed_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = load_user_confirmed()
    data[key] = version.strip()
    try:
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return True
    except OSError:
        return False


def lookup_pnp_firmware_versions(device_ids: list[str]) -> dict[str, str]:
    """Query DEVPKEY_Device_FirmwareVersion for instance IDs (Phase A)."""
    ids = [i.strip() for i in device_ids if (i or "").strip()]
    if not ids:
        return {}
    import bsod_runtime as rt

    payload = base64.b64encode(json.dumps(ids).encode("utf-8")).decode("ascii")
    use_pwsh = rt.powershell7_available()
    ps = _build_firmware_version_lookup_script(payload, parallel=use_pwsh)
    timeout = max(25, 6 + len(ids) // 3)
    ok, out = rt.run_powershell(ps, timeout=timeout, prefer_pwsh=use_pwsh)
    if not ok or not out:
        return {}
    try:
        mapping = json.loads(out)
    except json.JSONDecodeError:
        return {}
    if not isinstance(mapping, dict):
        return {}
    return {
        str(k): str(v).strip()
        for k, v in mapping.items()
        if v and str(v).strip()
    }


def _build_firmware_version_lookup_script(payload_b64: str, *, parallel: bool) -> str:
    header = f"""
$raw = [System.Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{payload_b64}'))
"""
    body = """
  $fw = (Get-PnpDeviceProperty -InstanceId $id -KeyName 'DEVPKEY_Device_FirmwareVersion' -EA SilentlyContinue).Data
  if ($fw) { [PSCustomObject]@{ Id = $id; Firmware = [string]$fw } }
"""
    if parallel:
        return header + f"""
$parsed = $raw | ConvertFrom-Json
if ($parsed -is [System.Array]) {{ $ids = $parsed }} else {{ $ids = @($parsed) }}
$results = @($ids | ForEach-Object -Parallel {{
  $id = [string]$_
  if (-not $id) {{ return $null }}
{body}
}} -ThrottleLimit 10)
$out = @{{}}
foreach ($r in $results) {{ if ($r) {{ $out[$r.Id] = $r.Firmware }} }}
$out | ConvertTo-Json -Compress
"""
    return header + """
$parsed = $raw | ConvertFrom-Json
if ($parsed -is [System.Array]) { $ids = $parsed } else { $ids = @($parsed) }
$out = @{}
foreach ($id in $ids) {
  if (-not $id) { continue }
  $fw = (Get-PnpDeviceProperty -InstanceId $id -KeyName 'DEVPKEY_Device_FirmwareVersion' -EA SilentlyContinue).Data
  if ($fw) { $out[[string]$id] = [string]$fw }
}
$out | ConvertTo-Json -Compress
"""


def _load_lghub_settings_json() -> dict | None:
    """Read-only parse of G HUB settings.db JSON blob (data.file)."""
    db_path = _local_appdata() / _LGHUB_DB
    if not db_path.is_file():
        return None
    try:
        import sqlite3

        conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
        try:
            row = conn.execute("SELECT file FROM data LIMIT 1").fetchone()
        finally:
            conn.close()
        if not row or not row[0]:
            return None
        blob = row[0]
        text = blob.decode("utf-8") if isinstance(blob, bytes) else str(blob)
        data = json.loads(text)
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError, sqlite3.Error, ValueError):
        return None


def _lghub_needles(vid: str, pid: str, product_tokens: list[str]) -> set[str]:
    needles = {
        vid.lower(),
        pid.lower(),
        f"{vid.lower()}:{pid.lower()}",
        f"vid_{vid.lower()}",
        f"pid_{pid.lower()}",
    }
    for tok in product_tokens:
        t = (tok or "").strip().lower()
        if len(t) >= 3:
            needles.add(t)
            needles.update(re.findall(r"[a-z0-9]{3,}", t))
    return needles


def _walk_json_for_firmware(
    obj: Any,
    *,
    needles: set[str],
    depth: int = 0,
) -> str:
    if depth > 14:
        return ""
    if isinstance(obj, dict):
        blob = json.dumps(obj, ensure_ascii=True).lower()
        if needles and not any(n in blob for n in needles):
            return ""
        for key, val in obj.items():
            if str(key).lower() in _LGHUB_FW_KEYS and isinstance(val, str):
                ver = val.strip()
                if ver and not ver.startswith("10.0."):
                    return ver
            hit = _walk_json_for_firmware(val, needles=needles, depth=depth + 1)
            if hit:
                return hit
    elif isinstance(obj, list):
        for item in obj[:120]:
            hit = _walk_json_for_firmware(item, needles=needles, depth=depth + 1)
            if hit:
                return hit
    return ""


def _read_lghub_firmware(
    vid: str,
    pid: str,
    *,
    product_tokens: list[str] | None = None,
) -> dict[str, Any]:
    data = _load_lghub_settings_json()
    if not data:
        return {}
    needles = _lghub_needles(vid, pid, list(product_tokens or []))
    ver = _walk_json_for_firmware(data, needles=needles)
    if not ver:
        return {}
    return {
        "version": ver,
        "source": "vendor_app_cache",
        "path": str(_local_appdata() / _LGHUB_DB),
    }


def _read_razer_firmware(vid: str, pid: str) -> dict[str, Any]:
    """Structured JSON under Razer app dirs (exclude Logs/)."""
    local = _local_appdata()
    token = f"{vid.lower()}:{pid.lower()}"
    needles = {
        vid.lower(),
        pid.lower(),
        token,
        f"vid_{vid.lower()}",
        f"pid_{pid.lower()}",
    }
    for rel in _VENDOR_JSON_ROOTS.get("razer", ()):
        root = local / rel.replace("/", os.sep)
        if not root.is_dir():
            continue
        try:
            files = [
                fp
                for fp in root.rglob("*.json")
                if fp.is_file()
                and "log" not in {p.lower() for p in fp.parts}
                and fp.stat().st_size <= 512_000
            ]
        except OSError:
            continue
        for fp in files[:80]:
            try:
                text = fp.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            low = text.lower()
            if not any(n in low for n in needles):
                continue
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, (dict, list)):
                ver = _walk_json_for_firmware(parsed, needles=needles)
                if ver:
                    return {
                        "version": ver,
                        "source": "vendor_app_cache",
                        "path": str(fp),
                    }
            ver = _scan_text_for_firmware(text, tokens=list(needles))
            if ver:
                return {
                    "version": ver,
                    "source": "vendor_app_cache",
                    "path": str(fp),
                }
    return {}


def _scan_text_for_firmware(blob: str, *, tokens: list[str]) -> str:
    if not blob:
        return ""
    low = blob.lower()
    if tokens and not any(t.lower() in low for t in tokens if t):
        return ""
    for pat in (
        _FW_VER_IN_TEXT,
        re.compile(r"\bfirmware\s+v?\s*([\d]+(?:\.[\d]+){1,4}[a-z]?)\b", re.I),
        re.compile(r'"firmwareVersion"\s*:\s*"([^"]+)"', re.I),
        re.compile(r'"fwVersion"\s*:\s*"([^"]+)"', re.I),
    ):
        m = pat.search(blob)
        if m:
            ver = m.group(1).strip()
            if ver and not ver.startswith("10.0."):
                return ver
    return ""


def read_vendor_app_firmware(
    vendor_key: str,
    *,
    device_id: str = "",
    product_tokens: list[str] | None = None,
) -> dict[str, Any]:
    """Best-effort read of installed firmware from vendor desktop app data (Phase B)."""
    vk = (vendor_key or "").strip().lower()
    vid, pid = usb_vid_pid(device_id)
    tokens = list(product_tokens or [])
    if vid and pid:
        tokens.extend([vid, pid, f"{vid}:{pid}".lower()])

    if vk == "logitech" and vid and pid:
        hit = _read_lghub_firmware(vid, pid, product_tokens=tokens)
        if hit:
            return hit

    if vk == "razer" and vid and pid:
        hit = _read_razer_firmware(vid, pid)
        if hit:
            return hit

    roots = _VENDOR_JSON_ROOTS.get(vk)
    if not roots:
        return {}
    tokens = [t for t in tokens if t and len(t) >= 3][:10]
    local = _local_appdata()
    for rel in roots:
        root = local / rel.replace("/", os.sep)
        if not root.is_dir():
            continue
        try:
            files = [
                fp
                for fp in root.rglob("*.json")
                if fp.is_file()
                and "log" not in {p.lower() for p in fp.parts}
                and fp.stat().st_size <= 512_000
            ]
        except OSError:
            continue
        for fp in files[:80]:
            try:
                text = fp.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            ver = _scan_text_for_firmware(text, tokens=tokens)
            if ver:
                return {
                    "version": ver,
                    "source": "vendor_app_cache",
                    "path": str(fp),
                }
    return {}


def resolve_installed_firmware(
    device: dict,
    *,
    pnp_firmware: dict[str, str] | None = None,
    user_cache: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Merge installed firmware from all local sources; pick strongest signal."""
    device_id = (device.get("device_id") or "").strip()
    driver_ver = (device.get("driver_version") or device.get("installed_version") or "").strip()
    vendor = (device.get("vendor_key") or "").strip().lower()
    cache = user_cache if user_cache is not None else load_user_confirmed()
    key = device_cache_key(device_id)

    user_ver = (cache.get(key) or "").strip()
    pnp_ver = ""
    if pnp_firmware and device_id:
        pnp_ver = (pnp_firmware.get(device_id) or "").strip()
        if not pnp_ver and device.get("parent_device_id"):
            pnp_ver = (pnp_firmware.get(device.get("parent_device_id") or "") or "").strip()

    app_hit = read_vendor_app_firmware(
        vendor,
        device_id=device_id,
        product_tokens=[
            t
            for t in (
                device.get("product_name") or "",
                device.get("resolved_name") or "",
                device.get("name") or "",
            )
            if t
        ],
    )
    app_ver = (app_hit.get("version") or "").strip()

    # Priority: user confirmed > PnP firmware property > vendor app > non-inbox driver string
    if user_ver:
        return {
            "installed": user_ver,
            "installed_source": "user_confirmed",
            "installed_detail": f"Saved by user ({key})",
        }
    if pnp_ver:
        return {
            "installed": pnp_ver,
            "installed_source": "pnp_firmware_property",
            "installed_detail": "Windows DEVPKEY_Device_FirmwareVersion",
        }
    if app_ver:
        return {
            "installed": app_ver,
            "installed_source": "vendor_app_cache",
            "installed_detail": app_hit.get("path") or "Vendor app data",
        }
    if driver_ver and not driver_ver.startswith("10.0."):
        return {
            "installed": driver_ver,
            "installed_source": "driver_version",
            "installed_detail": "Non-inbox driver version",
        }
    return {
        "installed": driver_ver or "—",
        "installed_source": "hid_driver",
        "installed_detail": "Windows HID/driver package only — MCU firmware not exposed",
    }
