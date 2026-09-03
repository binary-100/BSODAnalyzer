"""Drivers-tab hardware scan without event logs (extracted from bsod_analyzer)."""

from __future__ import annotations

from bsod_hardware_wmi import (
    get_bios_and_driver_versions,
    get_devices_with_driver_problems,
    get_devices_with_generic_driver,
    get_hardware_profile_wmi_bundle,
    get_pnp_entities_for_analysis,
    get_storage_and_system_context,
)
from bsod_crash_report import (
    build_hardware_enrichment_bundle,
    device_inventory_for_matching,
    enrich_bios_driver_info,
    get_wmi_monitor_edid_by_device_id,
)


def _gather_hardware_profile_legacy(progress_cb=None) -> dict:
    """Fallback when the combined WMI bundle query fails."""
    total = 8

    def report(step: int, msg: str) -> None:
        if progress_cb:
            progress_cb(step, total, msg)

    report(0, "Reading devices…")
    pnp_list = get_pnp_entities_for_analysis() or []
    report(1, "Detecting hardware…")
    system_ctx = get_storage_and_system_context(pnp_list)
    system_ctx["pnp_list"] = pnp_list
    report(2, "Reading driver inventory…")
    bios_driver_info = get_bios_and_driver_versions(include_all=False) or {}
    report(3, "Reading monitor & disk details…")
    monitor_edid = get_wmi_monitor_edid_by_device_id()
    enrich_bundle = build_hardware_enrichment_bundle(pnp_list, monitor_edid=monitor_edid)
    pnp_index = enrich_bundle["pnp_enrichment"]
    system_ctx["monitor_edid"] = monitor_edid
    system_ctx["pnp_enrichment"] = pnp_index
    bios_driver_info = enrich_bios_driver_info(bios_driver_info, pnp_index)
    report(4, "Checking generic and missing drivers…")
    inv = device_inventory_for_matching(bios_driver_info)
    devices_with_generic_driver = get_devices_with_generic_driver(
        pnp_list,
        inv,
        edid_map=monitor_edid,
        pnp_enrichment=pnp_index,
        disk_by_pnp_fragment=enrich_bundle.get("disk_by_pnp_fragment"),
    )
    devices_with_driver_problems = get_devices_with_driver_problems(
        pnp_list, pnp_enrichment=pnp_index
    )
    report(5, "Hardware scan complete.")
    return {
        "pnp_list": pnp_list,
        "system_ctx": system_ctx,
        "bios_driver_info": bios_driver_info,
        "devices_with_generic_driver": devices_with_generic_driver,
        "devices_with_driver_problems": devices_with_driver_problems,
        "ssd_firmware": [],
        "monitor_edid": monitor_edid,
        "pnp_enrichment": pnp_index,
        "disk_by_pnp_fragment": enrich_bundle.get("disk_by_pnp_fragment") or {},
    }


def gather_hardware_profile(progress_cb=None) -> dict:
    """
    Lightweight hardware/driver scan without event logs or minidump analysis.
    Used for the Drivers tab and generic-device driver lookup before any crash analysis.
    """
    total = 5

    def report(step: int, msg: str) -> None:
        if progress_cb:
            progress_cb(step, total, msg)

    report(0, "Reading hardware & drivers (WMI pass — may take up to a minute)…")
    bundle = get_hardware_profile_wmi_bundle()
    if not bundle:
        return _gather_hardware_profile_legacy(progress_cb)

    pnp_list = bundle["pnp_list"]
    bios_driver_info = bundle["bios_driver_info"]
    monitor_edid = bundle["monitor_edid"]
    disk_rows = bundle["disk_rows"]

    report(1, "Detecting hardware…")
    system_ctx = get_storage_and_system_context(pnp_list, wmi_bundle=bundle)
    system_ctx["pnp_list"] = pnp_list
    system_ctx["monitor_edid"] = monitor_edid

    report(2, "Enriching device names…")
    enrich_bundle = build_hardware_enrichment_bundle(
        pnp_list,
        monitor_edid=monitor_edid,
        disk_rows=disk_rows,
    )
    pnp_index = enrich_bundle["pnp_enrichment"]
    system_ctx["pnp_enrichment"] = pnp_index
    bios_driver_info = enrich_bios_driver_info(bios_driver_info, pnp_index)

    report(3, "Checking generic and missing drivers…")
    inv = device_inventory_for_matching(bios_driver_info)
    devices_with_generic_driver = get_devices_with_generic_driver(
        pnp_list,
        inv,
        edid_map=monitor_edid,
        pnp_enrichment=pnp_index,
        disk_by_pnp_fragment=enrich_bundle.get("disk_by_pnp_fragment"),
    )
    devices_with_driver_problems = get_devices_with_driver_problems(
        pnp_list, pnp_enrichment=pnp_index
    )
    report(4, "Hardware scan complete.")

    return {
        "pnp_list": pnp_list,
        "system_ctx": system_ctx,
        "bios_driver_info": bios_driver_info,
        "devices_with_generic_driver": devices_with_generic_driver,
        "devices_with_driver_problems": devices_with_driver_problems,
        "ssd_firmware": [],
        "monitor_edid": monitor_edid,
        "pnp_enrichment": pnp_index,
        "disk_by_pnp_fragment": enrich_bundle.get("disk_by_pnp_fragment") or {},
    }
