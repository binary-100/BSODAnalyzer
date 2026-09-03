"""
Persistent hardware / driver inventory cache for full-install mode only.

Stores a slim hardware profile as gzip-compressed JSON in SQLite (full install).
Legacy hardware_profile_cache.json is migrated on first read.
Portable mode never reads or writes this cache.
"""

from __future__ import annotations

import gzip
import json
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_LIVE_FP_CACHE_VALUE: str = ""
_LIVE_FP_CACHE_AT: float = 0.0
_LIVE_FP_CACHE_TTL_SEC = 600.0

import app_settings as app_set

_CACHE_VERSION = 2
_LEGACY_JSON = "hardware_profile_cache.json"
_SQLITE_NAME = "hardware_profile_cache.sqlite"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS device_cache (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    version INTEGER NOT NULL,
    cached_at TEXT NOT NULL,
    profile_gz BLOB NOT NULL,
    hw_fingerprint TEXT NOT NULL DEFAULT ''
);
"""


def _cache_dir() -> Path | None:
    if not app_set.allows_persistent_driver_data():
        return None
    d = app_set.full_install_data_dir()
    d.mkdir(parents=True, exist_ok=True)
    return d


def _sqlite_path() -> Path | None:
    d = _cache_dir()
    return (d / _SQLITE_NAME) if d else None


def _legacy_json_path() -> Path | None:
    d = _cache_dir()
    return (d / _LEGACY_JSON) if d else None


def _connect() -> sqlite3.Connection | None:
    path = _sqlite_path()
    if not path:
        return None
    con = sqlite3.connect(str(path), timeout=10)
    con.executescript(_SCHEMA)
    try:
        con.execute(
            "ALTER TABLE device_cache ADD COLUMN hw_fingerprint TEXT NOT NULL DEFAULT ''"
        )
    except sqlite3.OperationalError:
        pass
    return con


def _parse_cached_at(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        if value.endswith("Z"):
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        return datetime.fromisoformat(value)
    except ValueError:
        try:
            return datetime.strptime(value[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            return None


def max_age_days(settings: dict | None = None) -> int:
    s = settings if settings is not None else app_set.load_settings()
    try:
        days = int(s.get("device_cache_max_age_days", 30))
    except (TypeError, ValueError):
        days = 30
    return max(1, min(days, 365))


def is_cache_fresh(
    payload: dict | None = None,
    *,
    settings: dict | None = None,
) -> bool:
    if payload is None:
        payload = load_cache_payload()
    if not payload:
        return False
    cached_at = _parse_cached_at(payload.get("cached_at"))
    if not cached_at:
        return False
    if cached_at.tzinfo is None:
        cached_at = cached_at.replace(tzinfo=timezone.utc)
    age = datetime.now(timezone.utc) - cached_at
    return age.days < max_age_days(settings)


def cache_age_summary(payload: dict | None = None) -> str:
    if payload is None:
        payload = load_cache_payload()
    if not payload:
        return "No cached device list"
    cached_at = payload.get("cached_at") or "?"
    try:
        dt = _parse_cached_at(str(cached_at))
        if dt:
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            days = (datetime.now(timezone.utc) - dt).days
            return f"Cached {days} day(s) ago ({cached_at[:10]})"
    except (TypeError, ValueError):
        pass
    return f"Cached at {cached_at}"


def profile_from_payload(payload: dict) -> dict | None:
    prof = payload.get("profile")
    return prof if isinstance(prof, dict) else None


def _slim_profile(profile: dict) -> dict:
    bio = profile.get("bios_driver_info") or {}
    return {
        "pnp_list": profile.get("pnp_list") or [],
        "system_ctx": profile.get("system_ctx") or {},
        "bios_driver_info": bio,
        "devices_with_generic_driver": profile.get("devices_with_generic_driver") or [],
        "devices_with_driver_problems": profile.get("devices_with_driver_problems") or [],
        "pnp_enrichment": profile.get("pnp_enrichment")
        or (profile.get("system_ctx") or {}).get("pnp_enrichment")
        or {},
    }


def _encode_profile(profile: dict) -> bytes:
    raw = json.dumps(_slim_profile(profile), separators=(",", ":"), ensure_ascii=False)
    return gzip.compress(raw.encode("utf-8"), compresslevel=6)


def _decode_profile(blob: bytes) -> dict | None:
    try:
        text = gzip.decompress(blob).decode("utf-8")
        data = json.loads(text)
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None


def _row_to_payload(
    version: int,
    cached_at: str,
    profile: dict,
    *,
    hw_fingerprint: str = "",
) -> dict:
    payload = {
        "version": version,
        "cached_at": cached_at,
        "profile": profile,
    }
    if hw_fingerprint:
        payload["hw_fingerprint"] = hw_fingerprint
    return payload


def inventory_fingerprint(profile: dict | None) -> str:
    """Stable identity for cache invalidation when hardware/BIOS changes."""
    if not profile:
        return ""
    ctx = profile.get("system_ctx") or {}
    bio_root = profile.get("bios_driver_info") or {}
    bios = bio_root.get("bios") if isinstance(bio_root.get("bios"), dict) else bio_root
    if not isinstance(bios, dict):
        bios = {}
    parts = [
        (ctx.get("system_manufacturer") or "")[:48].strip().lower(),
        (ctx.get("system_model") or "")[:48].strip().lower(),
        (bios.get("version") or bio_root.get("version") or "")[:32].strip().lower(),
    ]
    uuid = (ctx.get("system_product_uuid") or "").strip().lower()
    if uuid and uuid not in ("none", "to be filled by o.e.m.", "default string"):
        parts.insert(0, uuid[:64])
    return "|".join(parts)


def cached_inventory_fingerprint(payload: dict | None = None) -> str:
    if payload is None:
        payload = load_cache_payload()
    if not payload:
        return ""
    return str(payload.get("hw_fingerprint") or "").strip()


def read_live_system_fingerprint(*, use_cache: bool = True) -> str:
    """Fast WMI identity check (no full PnP enumeration)."""
    global _LIVE_FP_CACHE_VALUE, _LIVE_FP_CACHE_AT
    if use_cache and _LIVE_FP_CACHE_VALUE:
        if (time.monotonic() - _LIVE_FP_CACHE_AT) < _LIVE_FP_CACHE_TTL_SEC:
            return _LIVE_FP_CACHE_VALUE
    try:
        from bsod_runtime import run_powershell
    except ImportError:
        return ""
    if run_powershell is None:
        return ""
    ps = r"""
$ErrorActionPreference = 'SilentlyContinue'
$cs = Get-CimInstance Win32_ComputerSystem -EA 0 | Select-Object -First 1 Manufacturer, Model
$bios = Get-CimInstance Win32_BIOS -EA 0 | Select-Object -First 1 SMBIOSBIOSVersion
$prod = Get-CimInstance Win32_ComputerSystemProduct -EA 0 | Select-Object -First 1 UUID
[PSCustomObject]@{
  UUID = [string]$prod.UUID
  Mfr = [string]$cs.Manufacturer
  Model = [string]$cs.Model
  Bios = [string]$bios.SMBIOSBIOSVersion
} | ConvertTo-Json -Compress
"""
    ok, out = run_powershell(ps, timeout=20)
    if not ok or not (out or "").strip():
        return ""
    try:
        data = json.loads(out.strip())
        if isinstance(data, list) and data:
            data = data[0]
        if not isinstance(data, dict):
            return ""
        parts = [
            (data.get("Mfr") or "")[:48].strip().lower(),
            (data.get("Model") or "")[:48].strip().lower(),
            (data.get("Bios") or "")[:32].strip().lower(),
        ]
        uuid = (data.get("UUID") or "").strip().lower()
        if uuid and uuid not in ("none", "ffffffff-ffff-ffff-ffff-ffffffffffff"):
            parts.insert(0, uuid[:64])
        fp = "|".join(parts)
        if fp and use_cache:
            _LIVE_FP_CACHE_VALUE = fp
            _LIVE_FP_CACHE_AT = time.monotonic()
        return fp
    except (json.JSONDecodeError, TypeError, ValueError):
        return ""


def invalidate_live_fingerprint_cache() -> None:
    global _LIVE_FP_CACHE_VALUE, _LIVE_FP_CACHE_AT
    _LIVE_FP_CACHE_VALUE = ""
    _LIVE_FP_CACHE_AT = 0.0


def live_hardware_changed_since_cache(
    payload: dict | None = None,
    *,
    profile: dict | None = None,
) -> bool:
    """True when a fresh cache may still be stale due to system changes."""
    if payload is None:
        payload = load_cache_payload()
    if not payload or not is_cache_fresh(payload):
        return False
    cached_fp = cached_inventory_fingerprint(payload)
    if not cached_fp:
        return False
    if profile:
        current = inventory_fingerprint(profile)
        if current and current == cached_fp:
            return False
    live_fp = read_live_system_fingerprint()
    return bool(live_fp and live_fp != cached_fp)


def _load_legacy_json_payload() -> dict | None:
    path = _legacy_json_path()
    if not path or not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and data.get("version") in (1, _CACHE_VERSION):
            return data
    except (json.JSONDecodeError, OSError):
        pass
    return None


def _migrate_legacy_json() -> dict | None:
    payload = _load_legacy_json_payload()
    if not payload or not profile_from_payload(payload):
        return None
    if save_profile(profile_from_payload(payload) or {}):
        legacy = _legacy_json_path()
        if legacy and legacy.is_file():
            try:
                legacy.unlink()
            except OSError:
                pass
        return load_cache_payload()
    return payload


def load_cache_payload() -> dict | None:
    try:
        con = _connect()
        if con:
            row = con.execute(
                "SELECT version, cached_at, profile_gz, hw_fingerprint "
                "FROM device_cache WHERE id = 1"
            ).fetchone()
            con.close()
            if row:
                prof = _decode_profile(row[2])
                if prof is not None:
                    fp = ""
                    if len(row) > 3:
                        fp = str(row[3] or "").strip()
                    if not fp:
                        fp = inventory_fingerprint(prof)
                    return _row_to_payload(
                        int(row[0]), str(row[1]), prof, hw_fingerprint=fp
                    )
    except sqlite3.Error:
        pass
    return _migrate_legacy_json()


def load_cached_profile() -> dict | None:
    payload = load_cache_payload()
    if not payload:
        return None
    return profile_from_payload(payload)


def save_profile(profile: dict) -> bool:
    if not _cache_dir():
        return False
    cached_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    blob = _encode_profile(profile)
    hw_fp = inventory_fingerprint(profile)
    try:
        con = _connect()
        if not con:
            return False
        con.execute(
            """
            INSERT INTO device_cache (id, version, cached_at, profile_gz, hw_fingerprint)
            VALUES (1, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                version = excluded.version,
                cached_at = excluded.cached_at,
                profile_gz = excluded.profile_gz,
                hw_fingerprint = excluded.hw_fingerprint
            """,
            (_CACHE_VERSION, cached_at, blob, hw_fp),
        )
        con.commit()
        con.close()
        legacy = _legacy_json_path()
        if legacy and legacy.is_file():
            try:
                legacy.unlink()
            except OSError:
                pass
        invalidate_live_fingerprint_cache()
        return True
    except sqlite3.Error:
        return False


def clear_cache() -> None:
    try:
        con = _connect()
        if con:
            con.execute("DELETE FROM device_cache")
            con.commit()
            con.close()
    except sqlite3.Error:
        pass
    path = _sqlite_path()
    if path and path.is_file():
        try:
            path.unlink()
        except OSError:
            pass
    legacy = _legacy_json_path()
    if legacy and legacy.is_file():
        try:
            legacy.unlink()
        except OSError:
            pass


def cache_storage_summary() -> dict[str, Any]:
    """Bytes on disk for diagnostics / maintenance report."""
    out: dict[str, Any] = {"backend": "sqlite", "bytes": 0, "compressed": True}
    path = _sqlite_path()
    if path and path.is_file():
        out["bytes"] = path.stat().st_size
    legacy = _legacy_json_path()
    if legacy and legacy.is_file():
        out["legacy_json_bytes"] = legacy.stat().st_size
    return out


def has_full_device_list(profile: dict | None = None) -> bool:
    if profile is None:
        profile = load_cached_profile()
    if not profile:
        return False
    rows = (profile.get("bios_driver_info") or {}).get("all_drivers") or []
    return len(rows) > 0
