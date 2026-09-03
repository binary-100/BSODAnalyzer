"""
On-disk driver catalog cache (Windows Update + OEM scrape).

Search uses live catalogs when the cache is missing or stale, then saves session
results to disk. A full deep refresh runs only via Tools → Refresh driver database.
"""

from __future__ import annotations

import json
import re
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator

import app_settings as app_set

_WU_FILE = "wu_driver_cache.json"
_OEM_FILE = "oem_catalog_cache.json"
_force_deep_catalog = False
_bound_system_ctx: dict | None = None


@contextmanager
def catalog_system_ctx_scope(system_ctx: dict | None) -> Iterator[None]:
    """Temporarily bind machine identity for portable per-unit cache paths."""
    global _bound_system_ctx
    prev = _bound_system_ctx
    _bound_system_ctx = dict(system_ctx) if system_ctx else None
    try:
        yield
    finally:
        _bound_system_ctx = prev


def bind_catalog_system_ctx(system_ctx: dict | None) -> None:
    global _bound_system_ctx
    _bound_system_ctx = dict(system_ctx) if system_ctx else None


def _effective_system_ctx(system_ctx: dict | None = None) -> dict | None:
    if system_ctx is not None:
        return system_ctx
    return _bound_system_ctx


def set_force_deep_catalog(force: bool) -> None:
    global _force_deep_catalog
    _force_deep_catalog = bool(force)


def is_force_deep_catalog() -> bool:
    return _force_deep_catalog


def should_use_disk_cache() -> bool:
    return app_set.allows_catalog_disk_cache() and not _force_deep_catalog


def _cache_dir(*, system_ctx: dict | None = None) -> Path | None:
    if not app_set.allows_catalog_disk_cache():
        return None
    ctx = _effective_system_ctx(system_ctx)
    d = app_set.catalog_cache_dir(system_ctx=ctx)
    if ctx and app_set.is_portable_layout():
        migrate_legacy_catalog_cache(ctx)
    return d


def needs_catalog_refresh(
    settings: dict | None = None,
    *,
    system_ctx: dict | None = None,
) -> bool:
    """True when disk cache is missing or stale (manual Refresh or post-scan save target)."""
    if not app_set.allows_catalog_disk_cache(settings):
        return False
    if not _read_json(_WU_FILE) and not _read_json(_OEM_FILE):
        return True
    return is_catalog_stale(settings, system_ctx=system_ctx)


def _read_json(name: str) -> dict | None:
    path = _cache_dir()
    if not path:
        return None
    fp = path / name
    if not fp.is_file():
        return None
    try:
        data = json.loads(fp.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (json.JSONDecodeError, OSError):
        return None


def _write_json(name: str, payload: dict) -> bool:
    path = _cache_dir()
    if not path:
        return False
    try:
        (path / name).write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return True
    except OSError:
        return False


def _parse_at(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        if value.endswith("Z"):
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def is_catalog_fresh(payload: dict | None = None, *, settings: dict | None = None) -> bool:
    if payload is None:
        wu = _read_json(_WU_FILE)
        oem = _read_json(_OEM_FILE)
        if wu and oem:
            w_at = _parse_at(wu.get("cached_at"))
            o_at = _parse_at(oem.get("cached_at"))
            if w_at and o_at:
                payload = wu if w_at <= o_at else oem
            else:
                payload = wu or oem
        else:
            payload = wu or oem
    if not payload:
        return False
    cached_at = _parse_at(payload.get("cached_at"))
    if not cached_at:
        return False
    if cached_at.tzinfo is None:
        cached_at = cached_at.replace(tzinfo=timezone.utc)
    age_days = (datetime.now(timezone.utc) - cached_at).days
    return age_days < app_set.catalog_max_age_days(settings)


def system_ctx_has_catalog_identity(system_ctx: dict | None) -> bool:
    """True when manufacturer/model (and ideally tag/SKU) are known enough to fingerprint."""
    return machine_fingerprint(system_ctx) != "unknown"


def is_catalog_stale(
    settings: dict | None = None,
    *,
    system_ctx: dict | None = None,
) -> bool:
    """True when disk cache is missing, incomplete, wrong machine, or older than max age."""
    if not app_set.allows_catalog_disk_cache(settings):
        return False
    ctx = _effective_system_ctx(system_ctx)
    with catalog_system_ctx_scope(ctx):
        wu = _read_json(_WU_FILE)
        oem = _read_json(_OEM_FILE)
    if not wu and not oem:
        return True
    if not wu:
        return True
    if ctx is not None:
        if wu and not cache_matches_machine(wu, ctx):
            return True
        if oem and not cache_matches_machine(oem, ctx):
            return True
    if not is_catalog_fresh(wu, settings=settings):
        return True
    if oem and not is_catalog_fresh(oem, settings=settings):
        return True
    return False


def should_prompt_catalog_refresh(
    settings: dict | None = None,
    *,
    system_ctx: dict | None = None,
) -> bool:
    s = settings if settings is not None else app_set.load_settings()
    # Portable: Search already builds session + on-disk WU/OEM cache beside the app.
    # Tools → Refresh driver database remains available; tab-switch prompt targets full install.
    if (s.get("install_mode") or "portable").strip().lower() != "full":
        return False
    if not s.get("catalog_auto_refresh_prompt", False):
        return False
    ctx = _effective_system_ctx(system_ctx)
    if not system_ctx_has_catalog_identity(ctx):
        return False
    return is_catalog_stale(s, system_ctx=ctx)


def machine_fingerprint(system_ctx: dict | None) -> str:
    """Stable identity for on-disk and session OEM/WU caches (model + machine-specific id)."""
    ctx = system_ctx or {}
    mfr = (ctx.get("system_manufacturer") or "").strip().lower()
    model = (ctx.get("system_model") or "").strip().lower()
    tag_raw = (
        (ctx.get("service_tag") or ctx.get("serial_number") or ctx.get("serial") or "")
        .strip()
    )
    tag = tag_raw.lower()
    try:
        import bsod_crash_report as bc

        if not bc._valid_pc_service_tag(tag_raw):
            tag = ""
    except ImportError:
        if tag in ("none", "default", "to be filled", "system serial", "system serial number"):
            tag = ""
    sku = (ctx.get("system_sku") or "").strip().lower()
    mtm = re.sub(
        r"[^a-z0-9]",
        "",
        (
            (ctx.get("machine_type") or ctx.get("baseboard_product") or "")
            .strip()
            .lower()
        ),
    )[:16]
    parts = [p for p in (mfr, model) if p]
    if tag and len(tag) >= 5:
        parts.append(f"tag:{tag}")
    elif sku:
        parts.append(f"sku:{sku}")
    elif mtm and len(mtm) >= 5:
        parts.append(f"mtm:{mtm}")
    return "|".join(parts) if parts else "unknown"


def fingerprint_cache_dirname(system_ctx: dict | None) -> str:
    """Filesystem-safe subfolder name for portable per-unit catalog cache."""
    fp = machine_fingerprint(system_ctx)
    if not fp or fp == "unknown":
        return "_unidentified"
    safe = re.sub(r'[<>:"/\\|?*]', "_", fp)
    return safe[:120] or "_unidentified"


def cache_matches_machine(blob: dict | None, system_ctx: dict | None) -> bool:
    """False when a cache file was saved for a different physical machine."""
    if not blob:
        return True
    stored = (blob.get("machine") or "").strip()
    if not stored:
        return True
    return stored == machine_fingerprint(system_ctx)


def _blob_usable_for_load(blob: dict | None, system_ctx: dict | None) -> bool:
    """Conservative load: blobs tagged for a machine require matching system_ctx."""
    if not blob:
        return False
    stored = (blob.get("machine") or "").strip()
    if not stored:
        return True
    if system_ctx is None:
        return False
    return cache_matches_machine(blob, system_ctx)


def load_wu_rows(
    system_ctx: dict | None = None,
) -> tuple[list[dict], str, dict | None]:
    """Return (rows, error_message, payload_or_none)."""
    ctx = _effective_system_ctx(system_ctx)
    with catalog_system_ctx_scope(ctx):
        blob = _read_json(_WU_FILE)
    if not blob:
        return [], "", None
    if not _blob_usable_for_load(blob, ctx):
        return [], "", None
    rows = blob.get("rows") or []
    if not isinstance(rows, list):
        rows = []
    return rows, str(blob.get("error") or ""), blob


def save_wu_rows(
    rows: list[dict],
    error: str = "",
    *,
    system_ctx: dict | None = None,
    rows_truncated: bool = False,
    rows_original_count: int | None = None,
) -> None:
    ctx = _effective_system_ctx(system_ctx)
    with catalog_system_ctx_scope(ctx):
        if not should_use_disk_cache() and not _force_deep_catalog:
            return
        payload: dict[str, Any] = {
            "cached_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "machine": machine_fingerprint(ctx),
            "rows": rows,
            "error": error,
            "cache_schema_version": 2,
        }
        if rows_truncated:
            payload["rows_truncated"] = True
            payload["rows_original_count"] = int(rows_original_count or len(rows))
        _write_json(_WU_FILE, payload)


def load_oem_offers(
    system_ctx: dict | None = None,
) -> tuple[list[dict], dict | None]:
    ctx = _effective_system_ctx(system_ctx)
    with catalog_system_ctx_scope(ctx):
        blob = _read_json(_OEM_FILE)
    if not blob:
        return [], None
    if not _blob_usable_for_load(blob, ctx):
        return [], None
    offers = blob.get("offers") or []
    if not isinstance(offers, list):
        offers = []
    return offers, blob


def save_oem_offers(
    offers: list[dict],
    *,
    system_ctx: dict | None = None,
    partial: bool = False,
    warmed_vendors: list[str] | None = None,
) -> None:
    ctx = _effective_system_ctx(system_ctx)
    with catalog_system_ctx_scope(ctx):
        if not _cache_dir(system_ctx=ctx):
            return
        payload: dict[str, Any] = {
            "cached_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "machine": machine_fingerprint(ctx),
            "offers": offers,
            "cache_schema_version": 2,
        }
        if partial:
            payload["partial"] = True
        if warmed_vendors:
            payload["warmed_vendors"] = list(warmed_vendors)
        _write_json(_OEM_FILE, payload)


def clear_catalog_cache() -> None:
    clear_wu_cache_file()
    clear_oem_cache_file()


def clear_wu_cache_file() -> None:
    path = _cache_dir()
    if not path:
        return
    fp = path / _WU_FILE
    if fp.is_file():
        try:
            fp.unlink()
        except OSError:
            pass


def clear_oem_cache_file() -> None:
    path = _cache_dir()
    if not path:
        return
    fp = path / _OEM_FILE
    if fp.is_file():
        try:
            fp.unlink()
        except OSError:
            pass


def catalog_age_summary(*, system_ctx: dict | None = None) -> str:
    ctx = _effective_system_ctx(system_ctx)
    with catalog_system_ctx_scope(ctx):
        wu = _read_json(_WU_FILE)
        oem = _read_json(_OEM_FILE)
    blob = wu or oem
    if not blob:
        return "Driver database not built yet"
    cached_at = blob.get("cached_at") or "?"
    try:
        dt = _parse_at(str(cached_at))
        if dt:
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            days = (datetime.now(timezone.utc) - dt).days
            summary = f"Driver database updated {days} day(s) ago ({str(cached_at)[:10]})"
            if wu and wu.get("rows_truncated"):
                orig = wu.get("rows_original_count")
                kept = len(wu.get("rows") or [])
                if orig and int(orig) > kept:
                    summary += f"; WU catalog capped at {kept} of {orig} rows"
            if oem and oem.get("partial"):
                warmed = oem.get("warmed_vendors") or []
                if warmed:
                    summary += f"; OEM partial ({', '.join(warmed)})"
                else:
                    summary += "; OEM partial"
            return summary
    except (TypeError, ValueError):
        pass
    return f"Driver database updated {cached_at}"


def _read_json_blob(name: str, fp: Path) -> dict | None:
    if not fp.is_file():
        return None
    try:
        data = json.loads(fp.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (json.JSONDecodeError, OSError):
        return None


def _stamp_legacy_blob(blob: dict, system_ctx: dict) -> dict:
    out = dict(blob)
    if not (out.get("machine") or "").strip():
        out["machine"] = machine_fingerprint(system_ctx)
    out.setdefault("cache_schema_version", 2)
    return out


def migrate_legacy_catalog_cache(system_ctx: dict | None) -> None:
    """One-time: stamp legacy blobs without machine; relocate PC-local flat cache to fingerprint subfolder."""
    if not system_ctx:
        return
    fp = machine_fingerprint(system_ctx)
    if fp == "unknown":
        return
    if not app_set.is_portable_layout():
        with catalog_system_ctx_scope(system_ctx):
            for name in (_WU_FILE, _OEM_FILE):
                blob = _read_json(name)
                if not blob or (blob.get("machine") or "").strip():
                    continue
                _write_json(name, _stamp_legacy_blob(blob, system_ctx))
        return
    base = app_set.maintenance_data_dir() / "driver_catalog"
    target = app_set.catalog_cache_dir(system_ctx=system_ctx)
    if not base.is_dir():
        return
    marker = target / ".migrated_v620"
    if marker.is_file():
        return
    target.mkdir(parents=True, exist_ok=True)
    for name in (_WU_FILE, _OEM_FILE):
        flat_fp = base / name
        dest_fp = target / name
        blob = _read_json_blob(name, flat_fp)
        if not blob:
            continue
        stored = (blob.get("machine") or "").strip()
        if stored and stored != fp:
            continue
        blob = _stamp_legacy_blob(blob, system_ctx)
        if dest_fp.is_file():
            continue
        try:
            dest_fp.write_text(json.dumps(blob, indent=2), encoding="utf-8")
            flat_fp.unlink(missing_ok=True)
        except OSError:
            pass
    try:
        marker.write_text(fp, encoding="utf-8")
    except OSError:
        pass


def portable_cache_mismatch_message(system_ctx: dict | None) -> str | None:
    """When legacy flat PC-local cache belongs to another unit."""
    if not system_ctx or not app_set.is_portable_layout():
        return None
    fp = machine_fingerprint(system_ctx)
    if fp == "unknown":
        return None
    base = app_set.maintenance_data_dir() / "driver_catalog"
    for name in (_WU_FILE, _OEM_FILE):
        blob = _read_json_blob(name, base / name)
        if not blob:
            continue
        stored = (blob.get("machine") or "").strip()
        if stored and stored != fp:
            return (
                "The saved driver database belongs to a different PC. "
                "Use Tools → Refresh driver database for this unit."
            )
    return None


def refresh_driver_database(
    system_ctx: dict,
    *,
    progress: Callable[[str], None] | None = None,
) -> tuple[bool, str]:
    """
    Deep refresh: clear caches and re-fetch WU + OEM (user-initiated only).
    Returns (ok, message).
    """
    import driver_catalog as dc

    def prog(msg: str) -> None:
        if progress:
            progress(msg)

    set_force_deep_catalog(True)
    try:
        with catalog_system_ctx_scope(system_ctx):
            clear_catalog_cache()
            dc.clear_wu_driver_cache()
            dc.clear_oem_cache()
            try:
                import catalog_ps_module as cps
                import product_version as pv
                if pv.is_v6_line():
                    cps.reset_mscatalog_session()
                else:
                    cps = None  # type: ignore[assignment]
            except ImportError:
                cps = None  # type: ignore[assignment]
            if cps is not None:
                prog("Updating Microsoft Update Catalog helper (MSCatalogLTS)…")
                dc.ensure_mscatalog_module_ready(force_gallery_check=True, progress=prog)
                cps.reset_mscatalog_session()
            prog("Querying Windows Update (full refresh)…")
            rows, err = dc.fetch_wu_driver_rows_deep()
            trunc, orig = dc.peek_session_rows_truncated()
            save_wu_rows(
                rows,
                err,
                system_ctx=system_ctx,
                rows_truncated=trunc,
                rows_original_count=orig if trunc else len(rows),
            )
            prog("Scanning PC maker driver catalog (full refresh)…")
            offers = dc.fetch_oem_driver_offers_deep(system_ctx)
            save_oem_offers(offers, system_ctx=system_ctx, partial=False)
            n_oem = len(offers)
            n_wu = len(rows)
            age = catalog_age_summary(system_ctx=system_ctx)
            return True, (
                f"Driver database refreshed.\n"
                f"Windows Update: {n_wu} optional driver row(s).\n"
                f"OEM catalog: {n_oem} package/link row(s).\n"
                f"{age}"
            )
    except Exception as e:  # noqa: BLE001
        return False, str(e)
    finally:
        set_force_deep_catalog(False)
