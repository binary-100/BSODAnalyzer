"""Live probe — mirrors GUI paths (Run Analysis, Search, disk cache) for debugging.

Usage:
  py -3 scripts/live_machine_probe.py --fast
  py -3 scripts/live_machine_probe.py --scan --max-devices 2
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import app_settings as app_set
import bsod_analyzer as core
import bsod_hardware_wmi as hw
import catalog_cache as ccat
import driver_catalog as dc
from live_probe_gating import chipset_platform_targets, run_gated_vendor_probes

_WU = ccat._WU_FILE
_OEM = ccat._OEM_FILE
_PROBE_POOL = ThreadPoolExecutor(max_workers=2)


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    return str(value)


def _call_with_timeout(fn, timeout_sec: float, *args, **kwargs) -> tuple[Any, str]:
    fut = _PROBE_POOL.submit(fn, *args, **kwargs)
    try:
        return fut.result(timeout=timeout_sec), ""
    except FuturesTimeout:
        fut.cancel()
        return None, f"timeout after {timeout_sec}s"
    except Exception as exc:  # noqa: BLE001
        return None, str(exc)


def _workflow_notes() -> dict[str, str]:
    return {
        "run_analysis": (
            "Crash/logs + gather_hardware_profile() — builds system_ctx, inventory, pnp_list. "
            "Does not write the driver database by itself."
        ),
        "search_for_driver_updates": (
            "Drivers tab → Search for driver updates (Include checked). Same as DriverCatalogWorker: "
            "live WU/OEM/vendor queries per device, then persist_session_catalog_cache() writes "
            "session WU rows + warmed OEM to disk (portable and full install). "
            "This IS your normal catalog build in portable mode — not a separate step."
        ),
        "refresh_driver_database": (
            "Tools → Refresh driver database ONLY: clears all caches, force-deep WU pull, "
            "full OEM vendor scrape (fetch_oem_driver_offers_deep). Use when stale, after USB "
            "move to another unit, or when you want a complete OEM rebuild — not required after "
            "every Search if Search already completed successfully."
        ),
    }


def _cache_file_summary(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        blob = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"path": str(path), "error": "unreadable"}
    rows = blob.get("rows") or blob.get("offers") or []
    return {
        "path": str(path),
        "bytes": path.stat().st_size,
        "cached_at": blob.get("cached_at"),
        "machine": blob.get("machine"),
        "row_count": len(rows) if isinstance(rows, list) else 0,
        "rows_truncated": blob.get("rows_truncated"),
        "partial": blob.get("partial"),
        "warmed_vendors": blob.get("warmed_vendors"),
    }


def _list_cache_locations(ctx: dict | None) -> dict[str, Any]:
    portable_base = app_set.portable_settings_dir() / "driver_catalog"
    out: dict[str, Any] = {
        "portable_settings_dir": str(app_set.portable_settings_dir()),
        "active_cache_dir": str(app_set.catalog_cache_dir(system_ctx=ctx)),
        "flat_legacy_dir": str(portable_base),
    }
    if ctx:
        with ccat.catalog_system_ctx_scope(ctx):
            out["active"] = {
                "wu": _cache_file_summary(app_set.catalog_cache_dir(system_ctx=ctx) / _WU),
                "oem": _cache_file_summary(app_set.catalog_cache_dir(system_ctx=ctx) / _OEM),
            }
    flat = {}
    for name in (_WU, _OEM):
        flat[name] = _cache_file_summary(portable_base / name)
    out["flat_legacy"] = flat
    return out


def _gather_profile() -> tuple[dict, float]:
    t0 = time.monotonic()
    prof = core.gather_hardware_profile()
    elapsed = time.monotonic() - t0
    return prof, elapsed


def _pick_scan_devices(prof: dict, *, max_devices: int) -> list[str]:
    """Prefer NVIDIA GPU, Realtek NIC, AMD/Intel chipset, then other devices."""
    names: list[str] = []
    inv = core.device_inventory_for_matching(prof.get("bios_driver_info"))
    pnp = prof.get("pnp_list") or []

    for row in inv:
        label = (row.get("display_name") or row.get("name") or "").lower()
        if "nvidia" in label and ("geforce" in label or "rtx" in label or "gtx" in label):
            n = (row.get("name") or row.get("display_name") or "").strip()
            if n and n not in names:
                names.append(n)
                break
    for row in inv:
        label = (row.get("display_name") or row.get("name") or "").lower()
        if "realtek" in label and ("2.5g" in label or "gaming" in label or "ethernet" in label):
            n = (row.get("name") or row.get("display_name") or "").strip()
            if n and n not in names:
                names.append(n)
                break

    try:
        from bsod_analyzer import CHIPSET_DEVICE_AMD, CHIPSET_DEVICE_INTEL
    except ImportError:
        CHIPSET_DEVICE_AMD = hw.CHIPSET_DEVICE_AMD
        CHIPSET_DEVICE_INTEL = hw.CHIPSET_DEVICE_INTEL

    ctx = prof.get("system_ctx") or {}
    for dev_name, _label in chipset_platform_targets(ctx):
        if dev_name not in names:
            names.append(dev_name)

    for row in inv:
        n = (row.get("name") or row.get("display_name") or "").strip()
        if n and n not in names:
            names.append(n)
        if len(names) >= max_devices:
            break
    return names[:max_devices]


def _run_search_simulation(prof: dict, *, max_devices: int) -> dict[str, Any]:
    ctx = dict(prof.get("system_ctx") or {})
    ctx["_gui_driver_catalog"] = True
    pnp = prof.get("pnp_list") or []
    bios = prof.get("bios_driver_info")
    inv = core.device_inventory_for_matching(bios)
    device_names = _pick_scan_devices(prof, max_devices=max_devices)
    t0 = time.monotonic()
    dc.set_gui_catalog_session(True)
    try:
        result = dc.build_multi_device_driver_comparison(
            device_names,
            pnp,
            inv,
            ctx,
            progress=None,
        )
        dc.persist_session_catalog_cache(ctx)
    finally:
        dc.set_gui_catalog_session(False)
    elapsed = time.monotonic() - t0
    devices = result.get("devices") or []
    return {
        "elapsed_sec": round(elapsed, 2),
        "device_names": device_names,
        "checked_count": result.get("checked_count", len(devices)),
        "update_count": result.get("update_count"),
        "results": [
            {
                "device_name": d.get("device_name"),
                "status": d.get("status"),
                "installed_version": d.get("installed_version"),
                "offer_count": len(d.get("offers") or []),
                "catalog_note": d.get("catalog_note"),
            }
            for d in devices
        ],
    }


def build_fast_report(*, network_timeout_sec: float = 20.0) -> dict[str, Any]:
    """Lightweight live checks — bounded time, hardware-gated vendor probes."""
    report: dict[str, Any] = {"version": core.VERSION, "mode": "fast"}

    ctx, ctx_err = _call_with_timeout(hw.quick_chipset_system_ctx, 30.0)
    if ctx is None:
        ctx = {}
    report["system_chipset"] = {
        "cpu_vendor": (ctx or {}).get("cpu_vendor"),
        "has_amd_chipset": (ctx or {}).get("has_amd_chipset"),
        "has_intel_chipset": (ctx or {}).get("has_intel_chipset"),
        "gpu_vendor": (ctx or {}).get("gpu_vendor"),
        "gather_error": ctx_err or "",
    }

    report["vendor_probes"] = run_gated_vendor_probes(
        ctx,
        run_probe=_call_with_timeout,
        network_timeout_sec=network_timeout_sec,
    )

    try:
        import fix_progress as fix_progress_mod

        crash_label, crash_dt = fix_progress_mod.resolve_last_crash()
        report["fix_progress"] = {
            "last_crash_label": crash_label,
            "last_crash_resolved": crash_dt.isoformat() if crash_dt else "",
        }
    except Exception as exc:  # noqa: BLE001
        report["fix_progress"] = {"error": str(exc)}

    return _json_safe(report)


def build_report(
    *,
    run_scan: bool,
    max_devices: int,
    fast: bool = False,
    network_timeout_sec: float = 25.0,
) -> dict[str, Any]:
    if fast:
        return build_fast_report(network_timeout_sec=network_timeout_sec)
    settings = app_set.load_settings()
    prof, profile_sec = _gather_profile()
    ctx = dict(prof.get("system_ctx") or {})
    if ctx:
        ccat.migrate_legacy_catalog_cache(ctx)
        ccat.bind_catalog_system_ctx(ctx)

    inv = core.device_inventory_for_matching(prof.get("bios_driver_info"))
    machine_fp = ccat.machine_fingerprint(ctx) if ctx else "unknown"

    chipset_block: dict[str, Any] = {}
    try:
        for dev_name, label in chipset_platform_targets(ctx):
            r = dc.build_chipset_platform_comparison(
                dev_name, ctx, inventory=inv,
            )
            offers = r.get("offers") or []
            vendor_ver = next(
                (
                    (o.get("version") or "").strip()
                    for o in offers
                    if (o.get("source") or "") == "vendor" and (o.get("version") or "").strip()
                ),
                "",
            )
            chipset_block[label] = {
                "pnp_anchor": bool((r.get("context") or {}).get("instance_id")),
                "catalog_note": r.get("catalog_note"),
                "offer_count": len(offers),
                "installed_version": r.get("installed_version"),
                "vendor_version": vendor_ver,
            }
    except Exception as e:
        chipset_block = {"error": str(e)}

    vendor_health: list[dict[str, Any]] = []
    try:
        import vendor_endpoint_health as veh

        for row in veh.run_health_check(ctx):
            vendor_health.append(
                {
                    "vendor": row.vendor,
                    "label": row.label,
                    "ok": row.ok,
                    "version_sample": row.version_sample,
                    "method": row.method,
                    "failures": row.failures[:3],
                }
            )
    except Exception as e:
        vendor_health = [{"error": str(e)}]

    fix_progress_block: dict[str, Any] = {}
    try:
        import fix_progress as fix_progress_mod

        crash_label, crash_dt = fix_progress_mod.resolve_last_crash()
        fix_progress_block = {
            "last_crash_label": crash_label,
            "last_crash_resolved": crash_dt.isoformat() if crash_dt else "",
        }
    except Exception as e:
        fix_progress_block = {"error": str(e)}

    vendor_probes = run_gated_vendor_probes(
        ctx,
        run_probe=lambda fn, _t: (fn(), ""),
        network_timeout_sec=network_timeout_sec,
    )

    report: dict[str, Any] = {
        "version": core.VERSION,
        "workflows": _workflow_notes(),
        "settings": {
            "install_mode": settings.get("install_mode"),
            "quick_check_mode": bool(settings.get("quick_check_mode")),
            "catalog_auto_refresh_prompt": settings.get("catalog_auto_refresh_prompt", True),
            "portable_data_note": (
                "Cache path follows the running BSODAnalyzer.exe folder. "
                "Dev probe (py scripts/…) uses repo root; BSODAnalyzer_v6\\BSODAnalyzer.exe uses BSODAnalyzer_v6\\BSODAnalyzer_portable\\."
            ),
        },
        "hardware_profile": {
            "gather_sec": round(profile_sec, 2),
            "manufacturer": ctx.get("system_manufacturer"),
            "model": ctx.get("system_model"),
            "service_tag": ctx.get("service_tag"),
            "fingerprint": machine_fp,
            "inventory_count": len(inv),
            "pnp_count": len(prof.get("pnp_list") or []),
        },
        "catalog_disk": {
            "cache_locations": _list_cache_locations(ctx),
            "age_summary": ccat.catalog_age_summary(system_ctx=ctx) if ctx else ccat.catalog_age_summary(),
            "stale": ccat.is_catalog_stale(system_ctx=ctx) if ctx else None,
            "needs_refresh": ccat.needs_catalog_refresh(system_ctx=ctx) if ctx else None,
            "wu_rows_loadable": len(ccat.load_wu_rows(ctx)[0]) if ctx else 0,
            "oem_offers_loadable": len(ccat.load_oem_offers(ctx)[0]) if ctx else 0,
            "portable_mismatch_message": ccat.portable_cache_mismatch_message(ctx) if ctx else None,
        },
        "chipset_quick": chipset_block,
        "vendor_health": vendor_health,
        "fix_progress": fix_progress_block,
        "vendor_probes": vendor_probes,
        "scan_simulation": None,
    }

    if run_scan and ctx:
        report["scan_simulation"] = _run_search_simulation(prof, max_devices=max_devices)
        report["catalog_disk_after_scan"] = {
            "age_summary": ccat.catalog_age_summary(system_ctx=ctx),
            "stale": ccat.is_catalog_stale(system_ctx=ctx),
            "cache_locations": _list_cache_locations(ctx),
        }

    return _json_safe(report)


def main() -> int:
    parser = argparse.ArgumentParser(description="BSOD Analyzer live machine probe")
    parser.add_argument(
        "--fast",
        action="store_true",
        help="Vendor probes only (bounded time; no WMI gather, no scan)",
    )
    parser.add_argument(
        "--scan",
        action="store_true",
        help="Run a short Search-for-updates simulation (network; persists like the GUI)",
    )
    parser.add_argument(
        "--max-devices",
        type=int,
        default=2,
        help="Max devices for --scan (default 2)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=25.0,
        help="Per-probe network timeout in seconds (default 25)",
    )
    args = parser.parse_args()
    report = build_report(
        run_scan=args.scan and not args.fast,
        max_devices=max(1, args.max_devices),
        fast=args.fast,
        network_timeout_sec=max(5.0, args.timeout),
    )
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
