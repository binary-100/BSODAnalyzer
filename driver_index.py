"""
Persistent driver/firmware check results (SQLite).

Replaces check_cache.json for full-install mode. Portable mode uses the same DB
only when use_driver_index is enabled.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

import app_settings as app_set

_LEGACY_CHECKS = "check_cache.json"
# Must match record_batch_results() JSON cap so Packages restore after restart.
_MAX_DETAIL_LEN = 48_000
_BATCH_READ_CHUNK = 500
_last_index_error: str | None = None
_last_index_read_gap_names: list[str] = []
_migration_attempted = False
_schema_initialized = False

_SCHEMA = """
CREATE TABLE IF NOT EXISTS device_checks (
    device_key TEXT PRIMARY KEY,
    device_name TEXT NOT NULL,
    installed_version TEXT,
    status TEXT NOT NULL,
    checked_at TEXT NOT NULL,
    fetched_at TEXT,
    detail TEXT
);
CREATE INDEX IF NOT EXISTS idx_device_checks_status ON device_checks(status);
CREATE TABLE IF NOT EXISTS firmware_checks (
    target_key TEXT PRIMARY KEY,
    target_label TEXT,
    status TEXT NOT NULL,
    installed_version TEXT,
    checked_at TEXT NOT NULL,
    fetched_at TEXT,
    detail TEXT
);
"""

_DEVICE_ROW_SQL = (
    "SELECT status, installed_version, checked_at, fetched_at, detail "
    "FROM device_checks WHERE device_key = ?"
)
_DEVICE_BATCH_SQL = (
    "SELECT device_key, status, installed_version, checked_at, fetched_at, detail "
    "FROM device_checks WHERE device_key IN ({placeholders})"
)
_FIRMWARE_ROW_SQL = (
    "SELECT status, installed_version, checked_at, fetched_at, detail "
    "FROM firmware_checks WHERE target_key = ?"
)
_FIRMWARE_BATCH_SQL = (
    "SELECT target_key, status, installed_version, checked_at, fetched_at, detail "
    "FROM firmware_checks WHERE target_key IN ({placeholders})"
)
_DEVICE_UPSERT_SQL = """
INSERT INTO device_checks (device_key, device_name, installed_version, status, checked_at, fetched_at, detail)
VALUES (?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(device_key) DO UPDATE SET
    device_name = excluded.device_name,
    installed_version = excluded.installed_version,
    status = excluded.status,
    checked_at = excluded.checked_at,
    fetched_at = excluded.fetched_at,
    detail = excluded.detail
"""
_FIRMWARE_UPSERT_SQL = """
INSERT INTO firmware_checks (target_key, target_label, status, installed_version, checked_at, fetched_at, detail)
VALUES (?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(target_key) DO UPDATE SET
    target_label = excluded.target_label,
    status = excluded.status,
    installed_version = excluded.installed_version,
    checked_at = excluded.checked_at,
    fetched_at = excluded.fetched_at,
    detail = excluded.detail
"""


def _db_path() -> Path | None:
    """SQLite path for full-install persistent data; None when persistence is disabled."""
    if not app_set.allows_persistent_driver_data():
        return None
    d = app_set.full_install_data_dir()
    d.mkdir(parents=True, exist_ok=True)
    return d / "driver_index.sqlite"


@contextmanager
def _managed_connect() -> Iterator[sqlite3.Connection | None]:
    con = _connect()
    try:
        yield con
    finally:
        if con is not None:
            con.close()


def _reset_session_flags() -> None:
    global _migration_attempted, _schema_initialized
    _migration_attempted = False
    _schema_initialized = False


def clear_index() -> None:
    path = _db_path()
    if path and path.is_file():
        try:
            path.unlink()
        except OSError:
            pass
    legacy = app_set.full_install_data_dir() / _LEGACY_CHECKS
    if legacy.is_file():
        try:
            legacy.unlink()
        except OSError:
            pass
    _reset_session_flags()


def _connect() -> sqlite3.Connection | None:
    global _schema_initialized
    path = _db_path()
    if not path:
        return None
    con = sqlite3.connect(str(path), timeout=30)
    if not _schema_initialized:
        con.executescript(_SCHEMA)
        _schema_initialized = True
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA busy_timeout=30000")
    return con


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _clamp_detail(detail: str) -> str:
    if not detail:
        return ""
    if len(detail) <= _MAX_DETAIL_LEN:
        return detail
    try:
        data = json.loads(detail)
        if isinstance(data, dict) and isinstance(data.get("offers"), list):
            offers = list(data["offers"])
            while offers:
                data["offers"] = offers
                encoded = json.dumps(data, ensure_ascii=False)
                if len(encoded) <= _MAX_DETAIL_LEN:
                    return encoded
                offers.pop()
            data["offers"] = offers
            return json.dumps(data, ensure_ascii=False)[:_MAX_DETAIL_LEN]
    except (json.JSONDecodeError, TypeError):
        pass
    return detail[:_MAX_DETAIL_LEN]


def device_key(name: str) -> str:
    return (name or "").strip().lower()


def peek_index_error() -> str | None:
    """Return and clear the last SQLite index write/error (for UI status)."""
    global _last_index_error
    err = _last_index_error
    _last_index_error = None
    return err


def peek_index_read_gaps() -> list[str]:
    """Return and clear device names that failed to load from the index."""
    global _last_index_read_gap_names
    gaps = list(_last_index_read_gap_names)
    _last_index_read_gap_names = []
    return gaps


def index_diagnostics_snapshot() -> dict[str, Any]:
    """Non-destructive read of last index read/write diagnostics (for export)."""
    return {
        "read_error": (_last_index_error or "")[:500] or None,
        "skipped_devices": list(_last_index_read_gap_names),
    }


def clear_index_diagnostics() -> None:
    global _last_index_error, _last_index_read_gap_names
    _last_index_error = None
    _last_index_read_gap_names = []


def _note_index_error(exc: sqlite3.Error) -> None:
    global _last_index_error
    _last_index_error = str(exc)


def _note_index_read_gaps(device_names: list[str]) -> None:
    global _last_index_read_gap_names
    for name in device_names:
        clean = (name or "").strip()
        if clean and clean not in _last_index_read_gap_names:
            _last_index_read_gap_names.append(clean)


def _device_row_to_dict(row: tuple) -> dict:
    return {
        "status": row[0],
        "installed_version": row[1],
        "checked_at": row[2],
        "fetched_at": row[3],
        "detail": row[4],
    }


def _firmware_row_to_dict(row: tuple) -> dict:
    return _device_row_to_dict(row)


def _ensure_migrated() -> None:
    global _migration_attempted
    if _migration_attempted:
        return
    if migrate_legacy_check_cache():
        _migration_attempted = True


def is_index_enabled(settings: dict | None = None) -> bool:
    """Whether SQLite index reads/writes apply for this session.

    Portable: only when ``use_driver_index`` is enabled (no DB unless opted in).
    Full install: when remember-checks is on and (use_driver_index or full-install mode).
    """
    s = settings if settings is not None else app_set.load_settings()
    if not app_set.allows_persistent_driver_data(s):
        return bool(s.get("use_driver_index"))
    if not s.get("remember_driver_firmware_checks"):
        return False
    return bool(s.get("use_driver_index")) or app_set.is_full_install_mode(s)


def migrate_legacy_check_cache() -> bool:
    """One-time import from check_cache.json into SQLite.

    Returns True when migration finished or nothing to do; False when legacy
    exists but could not be read (caller may retry later in the session).
    """
    if not app_set.allows_persistent_driver_data():
        return True
    legacy = app_set.full_install_data_dir() / _LEGACY_CHECKS
    if not legacy.is_file():
        return True
    try:
        data = json.loads(legacy.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return False
    if not isinstance(data, dict):
        return False
    now = _now_iso()
    device_rows: list[tuple] = []
    firmware_rows: list[tuple] = []
    for cache_key, entry in data.items():
        if not isinstance(entry, dict):
            continue
        kind = (entry.get("kind") or "").strip()
        item_key = cache_key
        if ":" in cache_key:
            prefix, item_key = cache_key.split(":", 1)
            if not kind:
                kind = prefix
        status = entry.get("status") or "none"
        ver = entry.get("installed_version") or ""
        fetched = entry.get("fetched_at") or now
        if kind == "firmware":
            extra = {
                k: v
                for k, v in entry.items()
                if k not in ("kind", "status", "installed_version", "fetched_at")
            }
            detail = ""
            if extra:
                try:
                    detail = _clamp_detail(json.dumps(extra, ensure_ascii=False))
                except (TypeError, ValueError):
                    detail = ""
            key = (item_key or "").strip()
            if key:
                firmware_rows.append(
                    (
                        key,
                        key[:200],
                        status,
                        ver,
                        now,
                        fetched,
                        detail,
                    )
                )
        elif kind == "driver":
            extra = {
                k: v
                for k, v in entry.items()
                if k not in ("kind", "status", "installed_version", "fetched_at")
            }
            detail = ""
            if extra:
                try:
                    detail = _clamp_detail(json.dumps(extra, ensure_ascii=False))
                except (TypeError, ValueError):
                    detail = ""
            key = device_key(item_key)
            name = (item_key or "").strip()
            if key and name:
                device_rows.append(
                    (key, name, ver, status, now, fetched, detail)
                )
    try:
        with _managed_connect() as con:
            if not con:
                return False
            if device_rows:
                con.executemany(_DEVICE_UPSERT_SQL, device_rows)
            if firmware_rows:
                con.executemany(_FIRMWARE_UPSERT_SQL, firmware_rows)
            con.commit()
    except sqlite3.Error as exc:
        _note_index_error(exc)
        return False
    try:
        legacy.unlink()
    except OSError:
        pass
    return True


def get_cached_status(device_name: str) -> dict | None:
    key = device_key(device_name)
    if not key:
        return None
    batch = get_cached_status_batch([device_name])
    return batch.get(key)


def get_cached_status_batch(device_names: list[str]) -> dict[str, dict]:
    """Batch read device check rows keyed by device_key."""
    _ensure_migrated()
    keys: list[str] = []
    for name in device_names:
        k = device_key(name)
        if k and k not in keys:
            keys.append(k)
    if not keys:
        return {}
    out: dict[str, dict] = {}
    key_to_name = {device_key(n): n for n in device_names if device_key(n)}
    try:
        with _managed_connect() as con:
            if not con:
                return {}
            for start in range(0, len(keys), _BATCH_READ_CHUNK):
                chunk = keys[start : start + _BATCH_READ_CHUNK]
                placeholders = ",".join("?" * len(chunk))
                try:
                    rows = con.execute(
                        _DEVICE_BATCH_SQL.format(placeholders=placeholders),
                        chunk,
                    ).fetchall()
                except sqlite3.Error as exc:
                    _note_index_error(exc)
                    _note_index_read_gaps(
                        [key_to_name[k] for k in chunk if k in key_to_name]
                    )
                    continue
                for row in rows:
                    out[row[0]] = _device_row_to_dict(row[1:])
    except sqlite3.Error as exc:
        _note_index_error(exc)
    return out


def get_firmware_cached(target_key: str) -> dict | None:
    key = (target_key or "").strip()
    if not key:
        return None
    batch = get_firmware_cached_batch([key])
    return batch.get(key)


def get_firmware_cached_batch(target_keys: list[str]) -> dict[str, dict]:
    """Batch read firmware check rows keyed by target_key."""
    _ensure_migrated()
    keys: list[str] = []
    for raw in target_keys:
        k = (raw or "").strip()
        if k and k not in keys:
            keys.append(k)
    if not keys:
        return {}
    out: dict[str, dict] = {}
    try:
        with _managed_connect() as con:
            if not con:
                return {}
            for start in range(0, len(keys), _BATCH_READ_CHUNK):
                chunk = keys[start : start + _BATCH_READ_CHUNK]
                placeholders = ",".join("?" * len(chunk))
                rows = con.execute(
                    _FIRMWARE_BATCH_SQL.format(placeholders=placeholders),
                    chunk,
                ).fetchall()
                for row in rows:
                    out[row[0]] = _firmware_row_to_dict(row[1:])
    except sqlite3.Error as exc:
        _note_index_error(exc)
        return {}
    return out


def save_check_result(
    device_name: str,
    status: str,
    *,
    installed_version: str = "",
    fetched_at: str = "",
    detail: str = "",
    con: sqlite3.Connection | None = None,
) -> None:
    key = device_key(device_name)
    if not key:
        return
    now = _now_iso()
    row = (
        key,
        device_name.strip(),
        installed_version or "",
        status,
        now,
        fetched_at or now,
        _clamp_detail(detail),
    )
    own_con = con is None
    try:
        if own_con:
            con = _connect()
        if not con:
            return
        con.execute(_DEVICE_UPSERT_SQL, row)
        if own_con:
            con.commit()
    except sqlite3.Error as exc:
        _note_index_error(exc)
    finally:
        if own_con and con is not None:
            con.close()


def save_firmware_check(
    target_key: str,
    status: str,
    *,
    installed_version: str = "",
    fetched_at: str = "",
    detail: str = "",
    target_label: str = "",
    con: sqlite3.Connection | None = None,
) -> None:
    key = (target_key or "").strip()
    if not key:
        return
    now = _now_iso()
    row = (
        key,
        (target_label or key)[:200],
        status,
        installed_version or "",
        now,
        fetched_at or now,
        _clamp_detail(detail),
    )
    own_con = con is None
    try:
        if own_con:
            con = _connect()
        if not con:
            return
        con.execute(_FIRMWARE_UPSERT_SQL, row)
        if own_con:
            con.commit()
    except sqlite3.Error as exc:
        _note_index_error(exc)
    finally:
        if own_con and con is not None:
            con.close()


def format_checked_at_short(iso_ts: str | None) -> str:
    """Human-readable 'last checked' for Notes column hints."""
    raw = (iso_ts or "").strip()
    if not raw:
        return "earlier"
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d")
    except ValueError:
        return raw[:10] if len(raw) >= 10 else raw


def _offers_from_detail(detail: str | None) -> list:
    raw = (detail or "").strip()
    if not raw:
        return []
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []
    if isinstance(payload, dict):
        offers = payload.get("offers")
        return offers if isinstance(offers, list) else []
    return []


def _catalog_entry_from_cached(name: str, cached: dict) -> dict | None:
    offers = _offers_from_detail(cached.get("detail"))
    status = (cached.get("status") or "none").strip() or "none"
    if not offers and status in ("none", "pending", ""):
        return None
    return {
        "device_name": name,
        "installed_version": (cached.get("installed_version") or "").strip() or "?",
        "offers": offers,
        "status": status,
        "_from_index": True,
        "_index_checked_at": cached.get("checked_at") or "",
    }


def _firmware_entry_from_cached(key: str, cached: dict) -> dict | None:
    offers = _offers_from_detail(cached.get("detail"))
    status = (cached.get("status") or "none").strip() or "none"
    if not offers and status in ("none", "pending", ""):
        return None
    return {
        "target_key": key,
        "installed_version": (cached.get("installed_version") or "").strip() or "?",
        "offers": offers,
        "status": status,
        "_from_index": True,
        "_index_checked_at": cached.get("checked_at") or "",
    }


def entry_with_index_firmware_packages(
    entry: dict | None, target_key: str
) -> dict | None:
    """Merge SQLite firmware offers when the session entry is missing or empty."""
    key = (target_key or "").strip()
    if not key:
        return entry
    indexed = firmware_entry_from_index(key)
    if entry:
        out = dict(entry)
        if not (out.get("offers") or []) and indexed and (indexed.get("offers") or []):
            out["offers"] = list(indexed.get("offers") or [])
            inst = (out.get("installed_version") or "").strip()
            if not inst or inst in ("?", "—"):
                out["installed_version"] = indexed.get("installed_version") or "?"
        return out
    if indexed:
        return dict(indexed)
    return None


def entry_with_index_packages(
    entry: dict | None, device_name: str
) -> dict | None:
    """Merge SQLite package offers when the session entry is missing or empty."""
    name = (device_name or "").strip()
    if not name:
        return entry
    indexed = catalog_entry_from_index(name)
    if entry:
        out = dict(entry)
        if not (out.get("offers") or []) and indexed and (indexed.get("offers") or []):
            out["offers"] = list(indexed.get("offers") or [])
            inst = (out.get("installed_version") or "").strip()
            if not inst or inst == "?":
                out["installed_version"] = indexed.get("installed_version") or "?"
        return out
    if indexed:
        return dict(indexed)
    return None


def catalog_entry_from_index(device_name: str) -> dict | None:
    """Packages panel payload from remembered checks (not a verified session scan)."""
    name = (device_name or "").strip()
    if not name:
        return None
    cached = get_cached_status(name)
    if not cached:
        return None
    return _catalog_entry_from_cached(name, cached)


def firmware_entry_from_index(target_key: str) -> dict | None:
    key = (target_key or "").strip()
    if not key:
        return None
    cached = get_firmware_cached(key)
    if not cached:
        return None
    return _firmware_entry_from_cached(key, cached)


def apply_index_hints_to_devices(
    devices: list[dict], settings: dict | None = None
) -> None:
    """Attach last-check hints only — never marks Updates available without a real scan."""
    if not is_index_enabled(settings):
        return
    _ensure_migrated()
    pending = [
        (dev, (dev.get("name") or "").strip())
        for dev in devices
        if not dev.get("_scan_verified")
    ]
    names = [name for _, name in pending if name]
    batch = get_cached_status_batch(names)
    for dev, name in pending:
        if not name:
            continue
        cached = batch.get(device_key(name))
        if not cached:
            continue
        status = (cached.get("status") or "").strip()
        if not status:
            continue
        dev["_index_last_status"] = status
        dev["_index_checked_at"] = cached.get("checked_at") or ""
        dev["_index_has_offers"] = bool(_offers_from_detail(cached.get("detail")))


def apply_index_hints_to_firmware_rows(
    rows: list[dict], settings: dict | None = None
) -> None:
    if not is_index_enabled(settings):
        return
    _ensure_migrated()
    pending = []
    for row in rows:
        if row.get("_scan_verified"):
            continue
        key = (row.get("key") or "").strip()
        if key in ("ssd:loading", ""):
            continue
        pending.append((row, key))
    batch = get_firmware_cached_batch([k for _, k in pending])
    for row, key in pending:
        cached = batch.get(key)
        if not cached:
            continue
        status = (cached.get("status") or "").strip()
        if not status:
            continue
        row["_index_last_status"] = status
        row["_index_checked_at"] = cached.get("checked_at") or ""
        row["_index_has_offers"] = bool(_offers_from_detail(cached.get("detail")))


def record_firmware_target_check(
    target_key: str,
    *,
    status: str,
    installed_version: str = "",
    offers: list | None = None,
    fetched_at: str = "",
    target_label: str = "",
) -> None:
    record_firmware_checks_batch(
        [
            {
                "target_key": target_key,
                "status": status,
                "installed_version": installed_version,
                "offers": offers,
                "target_label": target_label,
            }
        ],
        fetched_at=fetched_at,
    )


def record_firmware_checks_batch(
    checks: list[dict], *, fetched_at: str = ""
) -> None:
    """Persist multiple firmware check rows in one SQLite transaction."""
    if not checks:
        return
    _ensure_migrated()
    now = _now_iso()
    rows: list[tuple] = []
    for chk in checks:
        key = (chk.get("target_key") or "").strip()
        if not key:
            continue
        offers = chk.get("offers") or []
        detail = ""
        if offers:
            try:
                detail = _clamp_detail(
                    json.dumps({"offers": offers}, ensure_ascii=False)
                )
            except (TypeError, ValueError):
                detail = ""
        rows.append(
            (
                key,
                (chk.get("target_label") or key)[:200],
                chk.get("status") or "none",
                chk.get("installed_version") or "",
                now,
                fetched_at or now,
                detail,
            )
        )
    if not rows:
        return
    try:
        with _managed_connect() as con:
            if not con:
                return
            con.executemany(_FIRMWARE_UPSERT_SQL, rows)
            con.commit()
    except sqlite3.Error as exc:
        _note_index_error(exc)


def apply_index_packages_to_verified_firmware_rows(
    rows: list[dict], settings: dict | None = None
) -> None:
    """Attach persisted package offers for verified firmware rows (Packages panel)."""
    if not is_index_enabled(settings):
        return
    _ensure_migrated()
    pending = []
    for row in rows:
        if not row.get("_scan_verified"):
            continue
        key = (row.get("key") or "").strip()
        if not key or key in ("ssd:loading", "ssd:none"):
            continue
        pending.append((row, key))
    batch = get_firmware_cached_batch([k for _, k in pending])
    for row, key in pending:
        cached = batch.get(key)
        if not cached:
            continue
        indexed = _firmware_entry_from_cached(key, cached)
        if not indexed:
            continue
        offers = indexed.get("offers") or []
        if offers:
            row["_index_package_offers"] = offers
        inst = (indexed.get("installed_version") or "").strip()
        if inst and inst not in ("?", "—"):
            cur = (row.get("installed") or "").strip()
            if not cur or cur in ("?", "—", "Loading…"):
                row["installed"] = inst


def apply_index_packages_to_verified_devices(
    devices: list[dict], settings: dict | None = None
) -> None:
    """Attach persisted package offers for verified rows (Packages panel after restart)."""
    if not is_index_enabled(settings):
        return
    _ensure_migrated()
    pending = []
    for dev in devices:
        if not dev.get("_scan_verified"):
            continue
        name = (dev.get("name") or "").strip()
        if not name:
            continue
        pending.append((dev, name))
    batch = get_cached_status_batch([n for _, n in pending])
    for dev, name in pending:
        cached = batch.get(device_key(name))
        if not cached:
            continue
        indexed = _catalog_entry_from_cached(name, cached)
        if not indexed:
            continue
        offers = indexed.get("offers") or []
        if offers:
            dev["_index_package_offers"] = offers
        inst = (indexed.get("installed_version") or "").strip()
        if inst and inst != "?":
            if not (dev.get("_installed_at_scan") or "").strip():
                dev["_installed_at_scan"] = inst


def record_batch_results(devices: list[dict], *, fetched_at: str = "") -> None:
    """Persist multiple driver check rows in one SQLite transaction."""
    if not devices:
        return
    _ensure_migrated()
    now = _now_iso()
    rows: list[tuple] = []
    for entry in devices:
        name = (entry.get("device_name") or "").strip()
        if not name:
            continue
        key = device_key(name)
        offers = entry.get("offers") or []
        detail = ""
        if offers:
            try:
                detail = _clamp_detail(
                    json.dumps({"offers": offers}, ensure_ascii=False)
                )
            except (TypeError, ValueError):
                detail = ""
        rows.append(
            (
                key,
                name,
                entry.get("installed_version") or "",
                entry.get("status") or "none",
                now,
                fetched_at or now,
                detail,
            )
        )
    if not rows:
        return
    try:
        with _managed_connect() as con:
            if not con:
                return
            con.executemany(_DEVICE_UPSERT_SQL, rows)
            con.commit()
    except sqlite3.Error as exc:
        _note_index_error(exc)


def index_stats() -> dict[str, Any]:
    _ensure_migrated()
    try:
        with _managed_connect() as con:
            if not con:
                return {"total": 0, "outdated": 0, "firmware": 0}
            total = con.execute("SELECT COUNT(*) FROM device_checks").fetchone()[0]
            newer = con.execute(
                "SELECT COUNT(*) FROM device_checks WHERE status = 'newer'"
            ).fetchone()[0]
            fw = con.execute("SELECT COUNT(*) FROM firmware_checks").fetchone()[0]
            return {"total": total, "outdated": newer, "firmware": fw}
    except sqlite3.Error as exc:
        _note_index_error(exc)
        return {"total": 0, "outdated": 0, "firmware": 0}


def list_all_device_check_entries() -> list[dict]:
    """All persisted driver check rows (for export when session cache is empty)."""
    _ensure_migrated()
    out: list[dict] = []
    try:
        with _managed_connect() as con:
            if not con:
                return []
            cur = con.execute(
                "SELECT device_name, status, installed_version, checked_at, "
                "fetched_at, detail FROM device_checks "
                "ORDER BY device_name COLLATE NOCASE"
            )
            for row in cur.fetchall():
                name = (row[0] or "").strip()
                if not name:
                    continue
                cached = _device_row_to_dict(row[1:])
                ent = _catalog_entry_from_cached(name, cached)
                if ent:
                    out.append(ent)
    except sqlite3.Error as exc:
        _note_index_error(exc)
    return out


def list_all_firmware_check_entries() -> list[dict]:
    """All persisted firmware check rows (for export)."""
    _ensure_migrated()
    out: list[dict] = []
    try:
        with _managed_connect() as con:
            if not con:
                return []
            cur = con.execute(
                "SELECT target_key, target_label, status, installed_version, "
                "checked_at, fetched_at, detail FROM firmware_checks "
                "ORDER BY target_key COLLATE NOCASE"
            )
            for row in cur.fetchall():
                key = (row[0] or "").strip()
                if not key:
                    continue
                cached = _device_row_to_dict(row[2:])
                ent = _firmware_entry_from_cached(key, cached)
                if ent:
                    label = (row[1] or "").strip()
                    if label:
                        ent["target_label"] = label
                    out.append(ent)
    except sqlite3.Error as exc:
        _note_index_error(exc)
    return out
