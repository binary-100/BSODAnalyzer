"""Multi-device driver comparison batch pipeline (extracted from driver_catalog)."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Callable

from catalog_chipset_comparison import build_chipset_platform_comparison
from catalog_mscatalog_session import (
    _GUI_BATCH_INTER_PAUSE_SEC,
    _GUI_DEVICE_SCAN_BATCH_SIZE,
    begin_batch_mscatalog_query_cache,
    clear_batch_mscatalog_query_cache,
    ensure_mscatalog_module_ready,
    warm_batched_microsoft_online_store,
    warm_batched_mscatalog_queries,
    _gui_batched_online_store_enabled,
    _gui_catalog_mode,
    _gui_catalog_parallel_workers,
    _should_skip_online_driver_store,
)
from catalog_none_reason import (
    classify_none_reason,
    format_device_check_progress,
    possible_coverage_gap,
)
from catalog_offer_pipeline import _STATUS_RANK
from catalog_offer_status import summarize_offer_status


def _dc(name: str):
    """Lazy driver_catalog lookup — avoids import cycles during module load."""
    import driver_catalog as dc

    return getattr(dc, name)


_BATCH_CHECK_MAX_WORKERS = 8


def _batch_check_worker_count(device_count: int, *, gui_batch: bool = False) -> int:
    workers = max(1, min(_BATCH_CHECK_MAX_WORKERS, device_count))
    if gui_batch:
        workers = max(1, min(_gui_catalog_parallel_workers(), workers))
    return workers


def _run_device_check_batch(
    names: list[str],
    check_one: Callable[[str], dict],
    prog: Callable[[str], None],
    *,
    gui_batch: bool,
    done_offset: int = 0,
    total: int | None = None,
) -> list[dict]:
    """Check a list of device names with bounded parallelism (GUI batch-safe)."""
    results: list[dict] = []
    total = total if total is not None else len(names)
    workers = _batch_check_worker_count(len(names), gui_batch=gui_batch)
    if workers <= 1 or len(names) == 1:
        for i, name in enumerate(names, start=1):
            done = done_offset + i
            try:
                entry = check_one(name)
                results.append(entry)
                if _dc("_v6_catalog_enabled")():
                    prog(format_device_check_progress(name, entry, done=done, total=total))
                else:
                    prog(format_device_check_progress(name, entry))
            except Exception as e:  # noqa: BLE001
                err_entry = {
                    "device_name": name,
                    "installed_version": "?",
                    "installed_rows": [],
                    "offers": [],
                    "status": "error",
                    "error": str(e),
                    "context": {},
                }
                results.append(err_entry)
                if _dc("_v6_catalog_enabled")():
                    prog(format_device_check_progress(name, err_entry, done=done, total=total))
                else:
                    prog(format_device_check_progress(name, err_entry))
        return results

    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(check_one, n): n for n in names}
        done_in_batch = 0
        for fut in as_completed(futures):
            name = futures[fut]
            done_in_batch += 1
            done = done_offset + done_in_batch
            try:
                entry = fut.result()
                results.append(entry)
                if _dc("_v6_catalog_enabled")():
                    prog(format_device_check_progress(name, entry, done=done, total=total))
                else:
                    prog(format_device_check_progress(name, entry))
            except Exception as e:  # noqa: BLE001
                err_entry = {
                    "device_name": name,
                    "installed_version": "?",
                    "installed_rows": [],
                    "offers": [],
                    "status": "error",
                    "error": str(e),
                    "context": {},
                }
                results.append(err_entry)
                if _dc("_v6_catalog_enabled")():
                    prog(format_device_check_progress(name, err_entry, done=done, total=total))
                else:
                    prog(format_device_check_progress(name, err_entry))
    return results


def build_multi_device_driver_comparison(
    device_names: list[str],
    pnp_list: list | None,
    inventory: list | None,
    system_ctx: dict | None,
    progress: Callable[[str], None] | None = None,
) -> dict:
    """Check Microsoft / OEM / vendor sources for each device in the list."""
    ctx = _dc("extend_system_ctx_for_catalog")(dict(system_ctx or {}))
    inv = inventory

    def prog(msg: str) -> None:
        if progress:
            progress(msg)

    names: list[str] = []
    seen: set[str] = set()
    for raw in device_names:
        n = (raw or "").strip()
        if n and n not in seen:
            seen.add(n)
            names.append(n)
    skipped_firmware: list[str] = []
    scan_names: list[str] = []
    for name in names:
        dev_ctx = _dc("get_device_context_for_name")(name, pnp_list, inv, ctx)
        if _dc("is_driver_scan_excluded_ctx")(dev_ctx):
            skipped_firmware.append(name)
            continue
        scan_names.append(name)
    names = scan_names
    if not names:
        return {
            "devices": [],
            "fetched_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "checked_count": 0,
            "update_count": 0,
            "skipped_firmware_devices": skipped_firmware,
        }

    begin_batch_mscatalog_query_cache()
    try:
        import bsod_runtime as rt

        with rt.catalog_scan_performance_guard():
            return _build_multi_device_driver_comparison_body(
                names,
                skipped_firmware,
                pnp_list,
                inv,
                ctx,
                system_ctx,
                progress,
            )
    finally:
        clear_batch_mscatalog_query_cache()


def _build_multi_device_driver_comparison_body(
    names: list[str],
    skipped_firmware: list[str],
    pnp_list: list | None,
    inv: list | None,
    ctx: dict,
    system_ctx: dict | None,
    progress: Callable[[str], None] | None,
) -> dict:
    def prog(msg: str) -> None:
        if progress:
            progress(msg)

    results: list[dict] = []

    prog("Preparing Microsoft Update Catalog helper…")
    if _dc("_v6_catalog_enabled")():
        ensure_mscatalog_module_ready(progress=prog)
    prog("Querying Windows Update (once per batch)…")
    wu_rows, wu_err = _dc("_get_cached_wu_driver_rows")(ctx)
    if wu_err and not wu_rows:
        prog(wu_err[:120])
    if _should_skip_online_driver_store(system_ctx):
        prog(
            "Using Windows Update + OEM sources "
            "(skipping full online driver catalog for stability)."
        )
    else:
        _dc("ensure_online_driver_store_loaded")(progress=prog)
    if "_pnpsigned_version_index" not in ctx:
        ctx["_pnpsigned_version_index"] = _dc("_build_pnpsigned_version_index")()

    device_contexts: dict[str, dict] = {}
    for name in names:
        dev_ctx = _dc("get_device_context_for_name")(name, pnp_list, inv, ctx)
        if ctx.get("_pnpsigned_version_index"):
            dev_ctx["_pnpsigned_version_index"] = ctx["_pnpsigned_version_index"]
        dev_ctx["_batch_driver_check"] = True
        dev_ctx["_catalog_system_ctx"] = ctx
        if _gui_catalog_mode(system_ctx):
            dev_ctx["_gui_driver_catalog"] = True
        device_contexts[name] = dev_ctx

    if wu_rows:
        prog("Matching Windows Update packages to devices…")
        wu_prefilter = _dc("_batch_prefilter_wu_rows")(wu_rows, device_contexts)
    else:
        wu_prefilter = {name: [] for name in names}

    prog("Warming OEM catalog (once per batch)…")
    _dc("_warm_oem_session_cache")(system_ctx)

    gui_batch = bool((system_ctx or {}).get("_gui_driver_catalog"))
    if gui_batch:
        warm_batched_microsoft_online_store(device_contexts, system_ctx, progress=progress)
        warm_batched_mscatalog_queries(device_contexts, progress=progress)
        _dc("_warm_vendor_scrapes_for_contexts")(
            list(device_contexts.values()),
            progress=progress,
        )

    def check_one(name: str) -> dict:
        try:
            from bsod_hardware_wmi import CHIPSET_DEVICE_AMD, CHIPSET_DEVICE_INTEL
        except ImportError:
            CHIPSET_DEVICE_AMD = "__chipset_amd_platform__"
            CHIPSET_DEVICE_INTEL = "__chipset_intel_platform__"
        if name in (CHIPSET_DEVICE_AMD, CHIPSET_DEVICE_INTEL):
            comp = build_chipset_platform_comparison(name, ctx, None, inventory=inv)
        else:
            dev_ctx = device_contexts[name]
            dev_ctx["_prefiltered_wu_rows"] = wu_prefilter.get(name, [])
            if gui_batch and _dc("_v6_catalog_enabled")():
                prog(f"Checking {name[:44]}…")
            comp = _dc("_build_device_comparison_from_ctx")(
                dev_ctx,
                ctx,
                progress=prog if gui_batch else None,
            )
        offers = comp.get("offers") or []
        installed = comp.get("installed_version") or "?"
        status = summarize_offer_status(
            offers,
            device_ctx=comp.get("context") or dev_ctx,
        )
        dctx = comp.get("context") or dev_ctx
        gap = possible_coverage_gap(
            installed,
            offers,
            status=status,
            device_ctx=dctx,
        )
        none_reason = classify_none_reason(dctx, offers, status=status)
        if gap and none_reason in ("no_match", "informational_only", ""):
            none_reason = "coverage_gap"
        return {
            "device_name": name,
            "installed_version": installed,
            "installed_rows": comp.get("installed_rows") or [],
            "offers": offers,
            "status": status,
            "possible_coverage_gap": gap,
            "none_reason": none_reason,
            "context": comp.get("context") or {},
            "catalog_note": comp.get("catalog_note"),
            "chipset_bundle_components": comp.get("chipset_bundle_components") or [],
            "chipset_suite_version": comp.get("chipset_suite_version") or "",
        }

    use_scan_batches = (
        gui_batch
        and _gui_batched_online_store_enabled()
        and len(names) > _GUI_DEVICE_SCAN_BATCH_SIZE
    )
    if use_scan_batches:
        batch_size = _GUI_DEVICE_SCAN_BATCH_SIZE
        total = len(names)
        num_batches = (total + batch_size - 1) // batch_size
        prog(f"Checking {total} device(s) in {num_batches} automatic batch(es)…")
        for bi in range(num_batches):
            start = bi * batch_size
            chunk = names[start : start + batch_size]
            results.extend(
                _run_device_check_batch(
                    chunk,
                    check_one,
                    prog,
                    gui_batch=gui_batch,
                    done_offset=start,
                    total=total,
                )
            )
            if bi < num_batches - 1 and _GUI_BATCH_INTER_PAUSE_SEC > 0:
                time.sleep(_GUI_BATCH_INTER_PAUSE_SEC)
    else:
        workers = _batch_check_worker_count(len(names), gui_batch=gui_batch)
        prog(
            f"Checking {len(names)} device(s)"
            + (f" in parallel ({workers} workers)…" if workers > 1 else "…")
        )
        results.extend(
            _run_device_check_batch(
                names,
                check_one,
                prog,
                gui_batch=gui_batch,
                done_offset=0,
                total=len(names),
            )
        )

    if gui_batch and names:
        total = len(names)
        prog(f"Checked {total}/{total} — finalizing catalog…")

    if gui_batch:
        _dc("_augment_gap_devices_with_verified_catalog")(
            results, device_contexts, progress
        )

    results.sort(
        key=lambda r: (
            _STATUS_RANK.get(r.get("status") or "none", 99),
            (r.get("device_name") or "").lower(),
        )
    )
    update_count = sum(1 for r in results if r.get("status") == "newer")
    coverage_gap_count = sum(1 for r in results if r.get("possible_coverage_gap"))
    return {
        "devices": results,
        "fetched_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "checked_count": len(results),
        "update_count": update_count,
        "coverage_gap_count": coverage_gap_count,
        "skipped_firmware_devices": skipped_firmware,
    }
