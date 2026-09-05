"""Per-device catalog tier orchestration (extracted from driver_catalog)."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Callable

from catalog_chipset_comparison import build_chipset_platform_comparison
from catalog_device_context import (
    _ctx_is_chipset_component_plumbing,
    _device_is_amd_chipset_plumbing,
    _nvidia_gpu_driver_lookup_applicable,
    get_device_context_for_name,
    is_driver_scan_excluded_ctx,
)
from catalog_mscatalog_session import _gui_catalog_mode, is_quick_check_mode
from catalog_offer_pipeline import _finalize_catalog_offers, _installed_driver_date_from_ctx
from catalog_device_profiles import (
    collect_graphics_bundle_installed_components,
    ctx_supports_graphics_bundle_rollup,
    offer_is_oem_graphics_bundle,
)
from bundle_verification import attach_wrapper_row_bundle_rollup, enrich_offers_with_bundle_components
from catalog_tier_policy import (
    _ctx_gpu_or_network_catalog,
    _ctx_is_chipset_catalog,
    _manufacturer_gpu_lookup_uncertain,
    _should_skip_oem_after_manufacturer_tier,
    should_defer_microsoft_catalog,
)
from catalog_extended_fetch import _EXTENDED_VENDOR_KEYS
from catalog_tier_policy import _NETWORK_VENDOR_KEYS


def _dc(name: str):
    """Lazy driver_catalog lookup — avoids import cycles during module load."""
    import driver_catalog as dc

    return getattr(dc, name)


def catalog_device_source_path(
    ctx: dict,
    system_ctx: dict | None = None,
) -> str:
    """Export/diagnostic label for which catalog tiers ran for this device."""
    if _is_primary_gpu_display_manufacturer_authoritative(ctx, system_ctx):
        return "gpu_manufacturer_authoritative"
    if _ctx_is_chipset_catalog(ctx):
        return "chipset_tiered"
    vk = (ctx.get("vendor_key") or "").lower()
    pnp = (ctx.get("pnp_class") or "").lower()
    if vk == "realtek" and pnp == "net":
        return "network_realtek_full"
    if _ctx_gpu_or_network_catalog(ctx):
        return "gpu_or_network_tiered"
    return "standard_tiered"
def _is_primary_gpu_display_manufacturer_authoritative(
    ctx: dict,
    system_ctx: dict | None = None,
) -> bool:
    """Primary NVIDIA/AMD/Intel GPU display: manufacturer tier only (no OEM/WU/MSCatalog)."""
    pnp = (ctx.get("pnp_class") or "").lower()
    if pnp != "display":
        return False
    platform = _dc("_catalog_system_ctx_from")(ctx, system_ctx)
    vk = (ctx.get("vendor_key") or "").lower()
    label = (ctx.get("device_label") or "").lower()

    if vk == "nvidia" or "nvidia" in label or "geforce" in label:
        return (
            _nvidia_gpu_driver_lookup_applicable(ctx)
            and _dc("_manufacturer_vendor_lookup_applicable")("nvidia", platform)
        )
    if vk == "amd":
        if ctx.get("hw_category") == "chipset" or _device_is_amd_chipset_plumbing(ctx):
            return False
        return (
            _dc("_amd_vendor_version_lookup_applicable")(ctx)
            and _dc("_manufacturer_vendor_lookup_applicable")("amd", platform)
        )
    if vk == "intel":
        return _dc("_manufacturer_vendor_lookup_applicable")("intel", platform)
    return False
def _manufacturer_catalog_tasks_for_ctx(ctx: dict, system_ctx: dict | None) -> dict[str, Callable]:
    """Device-vendor sources only (tier 1 — before OEM)."""
    vk = (ctx.get("vendor_key") or "").lower()
    pnp = (ctx.get("pnp_class") or "").lower()
    tasks: dict[str, Callable] = {}
    platform = _dc("_catalog_system_ctx_from")(ctx, system_ctx)

    if vk == "nvidia" or (pnp == "display" and "nvidia" in (ctx.get("device_label") or "").lower()):
        if _nvidia_gpu_driver_lookup_applicable(ctx) and _dc("_manufacturer_vendor_lookup_applicable")(
            "nvidia", platform
        ):
            tasks["nvidia"] = lambda: _dc("fetch_nvidia_driver_offer")(ctx)
    component_plumbing = _ctx_is_chipset_component_plumbing(ctx)
    if vk == "amd" and _dc("_manufacturer_vendor_lookup_applicable")("amd", platform):
        if not component_plumbing:
            tasks["amd"] = lambda: _dc("fetch_amd_driver_offers")(ctx)
    if vk == "intel" and _dc("_manufacturer_vendor_lookup_applicable")("intel", platform):
        if not component_plumbing:
            tasks["intel"] = lambda: _dc("fetch_intel_driver_offers")(ctx)
    elif vk == "realtek" and _dc("_v6_catalog_enabled")() and _dc("_manufacturer_vendor_lookup_applicable")(
        "realtek", platform
    ):
        tasks["realtek"] = lambda: _dc("fetch_realtek_driver_offers")(ctx)
    elif vk in _NETWORK_VENDOR_KEYS and _dc("_v6_catalog_enabled")() and _dc("_manufacturer_vendor_lookup_applicable")(
        vk, platform
    ):
        tasks["network_vendor"] = lambda: _dc("fetch_network_vendor_offers")(ctx)
    elif vk in _EXTENDED_VENDOR_KEYS and _dc("_v6_catalog_enabled")() and _dc("_manufacturer_vendor_lookup_applicable")(
        vk, platform
    ):
        tasks["extended_vendor"] = lambda: _dc("fetch_extended_vendor_offers")(ctx)
    elif (
        vk
        and vk in _dc("_VENDOR_DRIVER_URLS")
        and _dc("_manufacturer_vendor_lookup_applicable")(vk, platform)
    ):
        tasks["vendor"] = lambda: _dc("fetch_generic_vendor_offer")(ctx)
    return tasks
def _run_catalog_source_tasks(
    tasks: dict[str, Callable],
    progress: Callable[[str], None] | None = None,
) -> list[dict]:
    """Run named catalog fetch tasks; parallel when multiple."""

    def prog(msg: str) -> None:
        if progress:
            progress(msg)

    if not tasks:
        return []
    offers: list[dict] = []
    if len(tasks) <= 1:
        for name, fn in tasks.items():
            try:
                chunk = fn() or []
                offers.extend(chunk)
                prog(f"Finished {name}…")
            except Exception as e:  # noqa: BLE001
                prog(f"{name} failed: {e}")
        return offers
    with ThreadPoolExecutor(max_workers=min(6, len(tasks))) as ex:
        futures = {ex.submit(fn): name for name, fn in tasks.items()}
        for fut in as_completed(futures):
            name = futures[fut]
            try:
                chunk = fut.result() or []
                offers.extend(chunk)
                prog(f"Finished {name}…")
            except Exception as e:  # noqa: BLE001
                prog(f"{name} failed: {e}")
    return offers
def _microsoft_catalog_task(
    ctx: dict,
    system_ctx: dict | None = None,
    *,
    allow_catalog_search: bool = True,
    include_informational: bool = False,
) -> Callable[[], list[dict]] | None:
    if is_quick_check_mode():
        return None
    prefiltered = ctx.get("_prefiltered_wu_rows")

    def _run() -> list[dict]:
        return _dc("fetch_microsoft_driver_offers")(
            ctx,
            prefiltered_rows=prefiltered,
            allow_catalog_search=allow_catalog_search,
            include_informational=include_informational,
            system_ctx=system_ctx,
        )

    return _run
def _skipped_firmware_driver_comparison(ctx: dict) -> dict:
    """Placeholder result when a firmware-class PnP device is excluded from driver scans."""
    installed = ctx.get("primary_version") or "?"
    name = ctx.get("target_device_name") or ctx.get("device_label") or ""
    return {
        "context": ctx,
        "installed_version": installed,
        "installed_date": _installed_driver_date_from_ctx(ctx),
        "installed_rows": ctx.get("installed_rows") or [],
        "offers": [],
        "fetched_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "device_name": name,
        "skipped_reason": "firmware_class",
        "status": "n/a",
    }
def build_device_driver_comparison(
    device_name: str,
    pnp_list: list | None,
    inventory: list | None,
    system_ctx: dict | None,
    progress: Callable[[str], None] | None = None,
) -> dict:
    """Compare installed vs catalog sources for one device (no BSOD analysis required)."""
    try:
        from bsod_hardware_wmi import CHIPSET_DEVICE_AMD, CHIPSET_DEVICE_INTEL
    except ImportError:
        CHIPSET_DEVICE_AMD = "__chipset_amd_platform__"
        CHIPSET_DEVICE_INTEL = "__chipset_intel_platform__"

    if device_name in (CHIPSET_DEVICE_AMD, CHIPSET_DEVICE_INTEL):
        return build_chipset_platform_comparison(
            device_name, system_ctx, progress, inventory=inventory,
        )

    ctx = get_device_context_for_name(device_name, pnp_list, inventory, system_ctx)
    if is_driver_scan_excluded_ctx(ctx):
        if progress:
            progress("Skipped — firmware-class device (use Firmware tab).")
        return _skipped_firmware_driver_comparison(ctx)
    return _build_device_comparison_from_ctx(ctx, system_ctx, progress=progress)
def _build_device_comparison_from_ctx(
    ctx: dict,
    system_ctx: dict | None,
    *,
    progress: Callable[[str], None] | None = None,
) -> dict:
    ctx = dict(ctx)
    if _gui_catalog_mode(system_ctx):
        ctx["_gui_driver_catalog"] = True
    ctx["_catalog_system_ctx"] = dict(system_ctx or {})
    ctx["video_controllers"] = ctx.get("video_controllers") or (
        (system_ctx or {}).get("video_controllers") or []
    )
    installed = _dc("_resolve_primary_installed_version")(ctx, system_ctx)
    ctx["primary_version"] = installed

    def prog(msg: str) -> None:
        if progress:
            progress(msg)

    offers: list[dict] = []
    manufacturer_tasks = _manufacturer_catalog_tasks_for_ctx(ctx, system_ctx)
    if manufacturer_tasks:
        prog("Querying manufacturer driver sources…")
        offers.extend(_run_catalog_source_tasks(manufacturer_tasks, progress=progress))
    elif not _ctx_is_chipset_catalog(ctx):
        prog("No manufacturer lookup for this device class…")

    gpu_mfr_only = _is_primary_gpu_display_manufacturer_authoritative(ctx, system_ctx)
    gpu_mfr_uncertain = _manufacturer_gpu_lookup_uncertain(
        offers, ctx, system_ctx=system_ctx
    )
    skip_oem = _should_skip_oem_after_manufacturer_tier(
        ctx, offers, installed, system_ctx=system_ctx
    )
    parallel_tasks: dict[str, Callable[[], list[dict]]] = {}
    if skip_oem:
        if gpu_mfr_only:
            if gpu_mfr_uncertain:
                prog("Skipping OEM — GPU manufacturer check uncertain; trying Microsoft catalog…")
            else:
                prog("Skipping OEM and Microsoft — GPU uses manufacturer catalog only")
        else:
            prog("Skipping OEM — manufacturer tier has a matching update")
    else:
        parallel_tasks["oem"] = lambda: _dc("fetch_oem_driver_offers")(ctx, system_ctx)

    if not is_quick_check_mode() and (not gpu_mfr_only or gpu_mfr_uncertain):
        prefiltered = ctx.get("_prefiltered_wu_rows")
        parallel_tasks["microsoft"] = lambda: _dc("fetch_microsoft_driver_offers")(
            ctx,
            prefiltered_rows=prefiltered,
            allow_catalog_search=False,
            include_informational=False,
            system_ctx=system_ctx,
        )

    if parallel_tasks:
        if "oem" in parallel_tasks and "microsoft" in parallel_tasks:
            prog("Querying OEM and Microsoft (WU + online catalog) in parallel…")
        elif "oem" in parallel_tasks:
            prog("Querying OEM catalog…")
        elif "microsoft" in parallel_tasks:
            prog("Querying Microsoft driver sources…")
        offers.extend(_run_catalog_source_tasks(parallel_tasks, progress=progress))

    defer_microsoft_catalog = (gpu_mfr_only and not gpu_mfr_uncertain) or should_defer_microsoft_catalog(
        offers, installed, ctx
    )
    if _ctx_is_chipset_component_plumbing(ctx):
        defer_microsoft_catalog = True
    if not is_quick_check_mode() and not defer_microsoft_catalog:
        try:
            catalog_offers = _dc("fetch_microsoft_catalog_search_offers")(ctx, max_results=2)
            offers.extend(catalog_offers or [])
            prog("Finished microsoft catalog…")
        except Exception as e:  # noqa: BLE001
            prog(f"microsoft catalog failed: {e}")
    elif not is_quick_check_mode() and defer_microsoft_catalog and not _ctx_is_chipset_component_plumbing(ctx):
        try:
            cache_offers = _dc("fetch_microsoft_catalog_search_offers")(
                ctx,
                max_results=1,
                cache_only=True,
            )
            if cache_offers:
                offers.extend(cache_offers)
                prog("Applied batch-warmed Microsoft Catalog match…")
        except Exception as exc:
            _dc("_log_catalog_skip")("batch-warmed MSCatalog cache", exc)
    elif not is_quick_check_mode() and parallel_tasks.get("microsoft"):
        prog("Finished microsoft (WU/store — OEM/vendor match found)…")

    seen = set()
    unique = []
    for o in offers:
        key = (o.get("source"), o.get("version"), o.get("title"))
        if key in seen:
            continue
        seen.add(key)
        unique.append(o)

    unique = _finalize_catalog_offers(
        unique,
        installed,
        device_ctx=ctx,
        installed_date=_installed_driver_date_from_ctx(ctx),
    )
    enrich_offers_with_bundle_components(unique)

    result = {
        "context": ctx,
        "installed_version": installed,
        "installed_date": _installed_driver_date_from_ctx(ctx),
        "installed_rows": ctx.get("installed_rows") or [],
        "offers": unique,
        "fetched_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "device_name": ctx.get("target_device_name") or ctx.get("device_label") or "",
    }
    if ctx_supports_graphics_bundle_rollup(ctx) and any(
        offer_is_oem_graphics_bundle(o) for o in unique
    ):
        inventory = (system_ctx or {}).get("_catalog_inventory") or []
        installed_components = collect_graphics_bundle_installed_components(
            inventory,
            primary_version=installed,
            video_controllers=ctx.get("video_controllers"),
        )
        attach_wrapper_row_bundle_rollup(
            result,
            installed_components=installed_components,
            offers=unique,
            device_ctx=ctx,
        )
    return result
