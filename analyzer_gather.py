"""Run Analysis data gathering (extracted from bsod_analyzer)."""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable


def _ba(name: str):
    """Lazy bsod_analyzer lookup — keeps mock.patch('bsod_analyzer.*') working in tests."""
    import bsod_analyzer as ba

    return getattr(ba, name)


def gather_firmware_inventory_for_gui(
    pnp_list: list | None,
    driver_rows: list | None = None,
) -> tuple[list, list]:
    """SSD + peripheral firmware rows (mirrors Firmware tab step 1 / SsdFirmwareWorker)."""
    ssd: list = []
    secondary: list = []
    try:
        ssd = _ba("get_ssd_firmware_inventory")() or []
    except Exception:
        ssd = []
    try:
        import firmware_peripheral_discovery as fpdisc

        secondary = fpdisc.discover_secondary_firmware_devices(
            list(pnp_list or []),
            list(driver_rows or []),
            query_pnp_firmware=True,
            has_bios=True,
        )
    except Exception:
        secondary = []
    return ssd, secondary


def gather_report_data(
    progress_cb: Callable[[int, str], None] | None = None,
    include_reliability: bool = True,
) -> tuple:
    """Gather all analysis inputs once and return (fmt_args, needs_config).

    fmt_args is the complete argument tuple for format_output(); callers can re-run
    format_output() with different widths without repeating expensive log/dump work.
    progress_cb(percent, message): optional callback for overall analysis progress (0–100).
    Partial failures are recorded in system_ctx["data_gaps"] for the GUI.
    """
    data_gaps: list[str] = []
    failed_tasks: set[str] = set()

    def emit(pct: int, msg: str) -> None:
        if progress_cb:
            try:
                progress_cb(pct, msg)
            except Exception:
                pass  # user progress callback; must not abort analysis

    emit(5, "Reading Windows event logs…")
    logged_in_user, primary_crashdumps, all_crashdumps_paths = _ba("get_logged_in_user_paths")()
    user_crashdumps_display = primary_crashdumps
    if len(all_crashdumps_paths) > 1:
        user_crashdumps_display = primary_crashdumps + " (and other user profiles)"

    results: dict = {}
    emit(8, "Querying event logs and crash dumps…")
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {
            executor.submit(_ba("query_bugcheck_events")): "events",
            executor.submit(_ba("query_boot_recovery_events")): "boot_recovery_pack",
            executor.submit(_ba("collect_kernel_minidumps")): "kernel_pack",
            executor.submit(_ba("check_full_dump")): "full_dump",
            executor.submit(_ba("list_dumps_from_paths"), all_crashdumps_paths, "Application"): "app_dumps",
            executor.submit(_ba("query_application_crashes")): "app_crash_events",
            executor.submit(_ba("get_bios_and_driver_versions")): "bios_driver_info",
            executor.submit(_ba("find_cdb")): "cdb_path",
        }
        for fut in as_completed(futures):
            name = futures[fut]
            try:
                results[name] = fut.result()
            except Exception as exc:
                failed_tasks.add(name)
                data_gaps.append(_ba("_analysis_gap_message")(name, exc))
                defaults = {
                    "events": ([], False),
                    "boot_recovery_pack": ([], True),
                    "kernel_pack": ([], _ba("get_crash_dump_settings")()),
                    "app_dumps": [],
                    "app_crash_events": [],
                    "full_dump": None,
                    "bios_driver_info": {},
                    "cdb_path": None,
                }
                results[name] = defaults.get(name)

    events_pack = results.get("events", ([], False))
    if isinstance(events_pack, tuple) and len(events_pack) == 2:
        events, events_query_failed = events_pack
    else:
        events, events_query_failed = events_pack if isinstance(events_pack, list) else [], True

    if events_query_failed and "events" not in failed_tasks:
        data_gaps.append(
            "Windows crash event log (System log query failed or timed out — "
            "run as Administrator and retry Run Analysis)"
        )

    boot_pack = results.get("boot_recovery_pack", ([], True))
    if isinstance(boot_pack, tuple) and len(boot_pack) == 2:
        boot_recovery_events, boot_recovery_failed = boot_pack
    else:
        boot_recovery_events = boot_pack if isinstance(boot_pack, list) else []
        boot_recovery_failed = "boot_recovery_pack" in failed_tasks

    kernel_pack = results.get("kernel_pack", ([], _ba("get_crash_dump_settings")()))
    if isinstance(kernel_pack, tuple) and len(kernel_pack) == 2:
        kernel_dumps, crash_settings = kernel_pack
    else:
        kernel_dumps = kernel_pack if isinstance(kernel_pack, list) else []
        crash_settings = _ba("get_crash_dump_settings")()

    full_dump = results.get("full_dump")
    app_dumps = results.get("app_dumps") or []
    app_crash_events = results.get("app_crash_events") or []
    bios_driver_info = results.get("bios_driver_info") or {}

    dump_val = crash_settings.get("crash_dump_enabled")
    dump_config = crash_settings.get("dump_type_label", "Unknown")
    if dump_val is None and not crash_settings.get("registry_read_ok"):
        dump_config = "Unable to read (run as Administrator)"

    needs_config = dump_val is None or dump_val == 0
    cdb_path = results.get("cdb_path")
    cdb_repair: dict = {"attempted": False, "repaired": False, "message": ""}
    local_cdb = _ba("_get_local_cdb_path")()
    if os.path.isfile(local_cdb) and not _ba("_cdb_engine_usable")(local_cdb):
        cdb_repair["attempted"] = True
        emit(18, "Repairing local Debugging Tools copy…")
        repaired, repair_msg = _ba("repair_local_cdb_engine_if_needed")()
        cdb_repair["repaired"] = repaired
        cdb_repair["message"] = repair_msg
        _ba("clear_cdb_path_cache")()
        cdb_path = _ba("find_cdb")()
        results["cdb_path"] = cdb_path

    minidump_prereqs = _ba("assess_minidump_prerequisites")(crash_settings)
    wer_recovery = _ba("reconcile_wer_dumpfile_gaps")(
        events,
        kernel_dumps,
        minidump_prereqs.get("directories") or [],
        minidump_prereqs=minidump_prereqs,
    )
    kernel_dumps = _ba("merge_recovered_kernel_dumps")(kernel_dumps, wer_recovery)
    for gap_msg in wer_recovery.get("data_gap_messages") or []:
        data_gaps.append(gap_msg)

    emit(22, "Scanning crash dumps and driver inventory…")

    def _full_driver_inventory_progress(msg: str) -> None:
        text = (msg or "Reading full driver inventory…").strip()
        emit(35, text[:120])

    emit(28, "Checking hardware errors and crash dumps…")
    group2_results: dict = {}
    with ThreadPoolExecutor(max_workers=6) as executor:
        futures2 = {
            executor.submit(_ba("query_whea_hardware_errors")): "whea_events",
            executor.submit(_ba("query_thermal_events")): "thermal_events",
            executor.submit(_ba("get_pnp_entities_for_analysis")): "pnp_list",
            executor.submit(
                _ba("get_all_installed_driver_devices"),
                _full_driver_inventory_progress,
                sequential=True,
            ): "full_driver_inventory",
        }
        if include_reliability:
            futures2[executor.submit(_ba("query_reliability_livekernel_bundle"))] = "reliability_ctx"
        if cdb_path and kernel_dumps:

            def _minidump_progress(done: int, total: int) -> None:
                pct = 28 + int(42 * done / max(total, 1))
                emit(min(pct, 69), f"Analyzing minidumps ({done}/{total})…")

            futures2[
                executor.submit(
                    _ba("analyze_recent_minidumps"),
                    kernel_dumps,
                    cdb_path,
                    3,
                    _minidump_progress,
                )
            ] = "windbg_analysis"

        for fut in as_completed(futures2):
            name = futures2[fut]
            try:
                group2_results[name] = fut.result()
            except Exception as exc:
                failed_tasks.add(name)
                data_gaps.append(_ba("_analysis_gap_message")(name, exc))
                if name in ("whea_events", "thermal_events", "pnp_list", "full_driver_inventory"):
                    group2_results[name] = []
                elif name == "reliability_ctx":
                    group2_results[name] = {
                        "livekernel": [],
                        "wer_errors": [],
                        "stability_index": None,
                        "_query_failed": True,
                    }
                else:
                    group2_results[name] = None

    whea_events = group2_results.get("whea_events", [])
    thermal_events = group2_results.get("thermal_events", [])
    windbg_analysis = group2_results.get("windbg_analysis")
    pnp_list = group2_results.get("pnp_list", [])
    full_driver_rows = group2_results.get("full_driver_inventory") or []
    if full_driver_rows:
        bios_driver_info = dict(bios_driver_info)
        bios_driver_info["all_drivers"] = full_driver_rows

    if kernel_dumps:
        if not cdb_path:
            data_gaps.append(
                "Minidumps were found but no working debugger engine is installed "
                "(Advanced tab → Install Debugging Tools, or install WinDbg from Microsoft Store)."
            )
        elif windbg_analysis:
            all_a = windbg_analysis.get("all_analyses") or []
            if all_a and not any(
                a.get("faulting_driver") or a.get("bugcheck_code") or a.get("raw")
                for a in all_a
            ):
                data_gaps.append(
                    "Minidump files were found but debugger !analyze returned no results "
                    "(Advanced tab → Update Debugging Tools)."
                )
        local_cdb = _ba("_get_local_cdb_path")()
        if (
            os.path.isfile(local_cdb)
            and not _ba("_cdb_engine_usable")(local_cdb)
            and cdb_path
            and os.path.normcase(cdb_path) != os.path.normcase(local_cdb)
            and not cdb_repair.get("repaired")
        ):
            data_gaps.append(
                "Local Debugging Tools copy is incomplete; analysis used the WinDbg app debugger."
            )
        elif cdb_repair.get("repaired"):
            data_gaps.append(cdb_repair.get("message") or "Repaired local Debugging Tools copy.")

    if include_reliability:
        reliability_ctx = group2_results.get("reliability_ctx")
    else:
        reliability_ctx = {"livekernel": [], "wer_errors": [], "stability_index": None}

    if reliability_ctx is None:
        reliability_ctx = {"livekernel": [], "wer_errors": [], "stability_index": None}
    if include_reliability and reliability_ctx.get("_query_failed"):
        data_gaps.append(
            "Reliability / Live Kernel events could not be read "
            "(PowerShell failed or returned no data — run as Administrator)."
        )
        reliability_ctx = {
            k: v for k, v in reliability_ctx.items() if not str(k).startswith("_")
        }
    reliability_ctx = dict(reliability_ctx)
    reliability_ctx["boot_recovery"] = boot_recovery_events
    if boot_recovery_failed and "boot_recovery_pack" not in failed_tasks:
        data_gaps.append(
            "Boot / recovery event log could not be read "
            "(Startup Repair or Kernel-Boot query failed — run as Administrator)."
        )

    if "pnp_list" in failed_tasks:
        data_gaps.append(_ba("_analysis_gap_message")("pnp_list"))

    emit(72, "Reading storage and system details…")
    try:
        wmi_bundle = _ba("get_report_storage_wmi_bundle")()
        system_ctx = _ba("get_storage_and_system_context")(pnp_list, wmi_bundle=wmi_bundle)
    except Exception as exc:
        failed_tasks.add("storage_context")
        data_gaps.append(_ba("_analysis_gap_message")("storage_context", exc))
        system_ctx = _ba("get_storage_and_system_context")(pnp_list)

    system_ctx = dict(system_ctx or {})
    system_ctx["pnp_list"] = pnp_list

    emit(78, "Enriching device names…")
    monitor_edid: dict = {}
    enrich_bundle: dict = {"pnp_enrichment": {}, "disk_by_pnp_fragment": {}}
    try:
        monitor_edid = _ba("get_wmi_monitor_edid_by_device_id")()
        enrich_bundle = _ba("build_hardware_enrichment_bundle")(pnp_list, monitor_edid=monitor_edid)
        system_ctx["monitor_edid"] = monitor_edid
        system_ctx["pnp_enrichment"] = enrich_bundle.get("pnp_enrichment") or {}
        bios_driver_info = _ba("enrich_bios_driver_info")(
            bios_driver_info,
            enrich_bundle.get("pnp_enrichment") or {},
        )
    except Exception as exc:
        failed_tasks.add("pnp_enrichment")
        data_gaps.append(_ba("_analysis_gap_message")("pnp_enrichment", exc))

    pnp_index = enrich_bundle.get("pnp_enrichment") or {}
    inv = _ba("device_inventory_for_matching")(bios_driver_info)
    devices_with_driver_problems = _ba("get_devices_with_driver_problems")(
        pnp_list, pnp_enrichment=pnp_index
    )
    devices_with_generic_driver = _ba("get_devices_with_generic_driver")(
        pnp_list,
        inv,
        edid_map=monitor_edid,
        pnp_enrichment=pnp_index,
        disk_by_pnp_fragment=enrich_bundle.get("disk_by_pnp_fragment"),
    )

    emit(88, "Reading firmware inventory…")
    driver_rows_for_fw = bios_driver_info.get("all_drivers") or full_driver_rows or []
    try:
        ssd_firmware, secondary_firmware = gather_firmware_inventory_for_gui(
            pnp_list,
            driver_rows_for_fw,
        )
    except Exception as exc:
        failed_tasks.add("firmware_inventory")
        data_gaps.append(_ba("_analysis_gap_message")("firmware_inventory", exc))
        ssd_firmware, secondary_firmware = [], []
    system_ctx["ssd_firmware"] = ssd_firmware
    system_ctx["secondary_firmware"] = secondary_firmware

    emit(91, "Parsing extended log attribution (WER, setupapi, CBS)…")
    try:
        import log_attribution as logattr

        system_ctx["extended_log_attribution"] = logattr.collect_extended_log_attribution(
            events,
            windbg_analysis=windbg_analysis,
            boot_recovery=boot_recovery_events,
            wer_dump_recovery=wer_recovery,
        )
    except Exception as exc:
        failed_tasks.add("extended_log_attribution")
        data_gaps.append(_ba("_analysis_gap_message")("extended_log_attribution", exc))

    emit(93, "Verifying crash-linked drivers…")
    try:
        import driver_verification as drvver

        system_ctx["driver_verification"] = drvver.run_driver_verification_pipeline(
            events,
            windbg_analysis,
            bios_driver_info,
            pnp_list=pnp_list,
            problem_devices=devices_with_driver_problems,
            generic_devices=devices_with_generic_driver,
            boot_recovery=reliability_ctx.get("boot_recovery") or [],
            system_ctx=system_ctx,
        )
    except Exception as exc:
        failed_tasks.add("driver_verification")
        data_gaps.append(
            f"Crash-linked driver verification ({str(exc).strip()[:80] or type(exc).__name__})"
        )
        system_ctx["driver_verification"] = {"suspects": [], "lines": [], "has_suspects": False}

    gap_msg = _ba("minidump_without_bugcheck_gap")(
        kernel_dumps,
        events,
        events_query_failed=events_query_failed,
    )
    if gap_msg:
        data_gaps.append(gap_msg)

    if data_gaps:
        system_ctx["data_gaps"] = list(dict.fromkeys(data_gaps))
    if cdb_repair.get("attempted"):
        system_ctx["cdb_repair"] = cdb_repair
    system_ctx["minidump_prerequisites"] = minidump_prereqs
    if wer_recovery.get("recovered_count"):
        system_ctx["wer_dump_recovery"] = wer_recovery

    emit(95, "Finalizing analysis…")

    if not include_reliability:
        reliability_ctx = {
            "livekernel": [],
            "wer_errors": [],
            "stability_index": None,
            "boot_recovery": boot_recovery_events,
        }

    fmt_args = (
        events,
        kernel_dumps,
        full_dump,
        app_dumps,
        windbg_analysis,
        whea_events,
        thermal_events,
        dump_config,
        dump_val,
        needs_config,
        logged_in_user,
        user_crashdumps_display,
        app_crash_events,
        bios_driver_info,
        system_ctx,
        devices_with_driver_problems,
        devices_with_generic_driver,
        reliability_ctx,
    )
    return fmt_args, needs_config
