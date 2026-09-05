#!/usr/bin/env python3
"""
Windows BSOD & Crash Analyzer
Analyzes Windows event logs (works independently - no dump required) and crash dumps.
Requests Administrator elevation for full log access.

v4.1: Driver comparison (Microsoft / OEM / vendor) with optional restore point and backup.
v4: Likely cause type, System device lists, crash-related highlights, guided driver updates.
v3.1: Single portable exe with bundled WinDbg/CDB engine.

REMINDER: After any change, recompile (`build_ci.bat` from the project root, or `run_tests.bat` then `build_and_deploy_v6.bat`).
"""
VERSION = "6.5.33"

import ctypes
import os
import sys
from datetime import datetime
from pathlib import Path

from bsod_runtime import (
    configure_console_encoding,
    console_print,
    ensure_cli_console,
    export_report_to_file,
    get_logged_in_user_paths,
    pause_before_exit,
    run_powershell,
)
from bsod_events import (
    query_application_crashes,
    query_boot_recovery_events,
    query_bugcheck_events,
    query_reliability_livekernel_bundle,
    query_thermal_events,
    query_whea_hardware_errors,
)
from bsod_hardware_wmi import (
    CHIPSET_DEVICE_AMD,
    CHIPSET_DEVICE_INTEL,
    chipset_driver_catalog_entries,
    get_all_installed_driver_devices,
    get_bios_and_driver_versions,
    get_devices_with_driver_problems,
    get_devices_with_generic_driver,
    get_pnp_entities_for_analysis,
    get_report_storage_wmi_bundle,
    get_ssd_firmware_inventory,
    get_storage_and_system_context,
    _extract_vendor_from_string,  # noqa: F401 — used by GUI via core
    _parse_json_date,
)

from bsod_minidump import (
    MINIDUMP_DIR,
    assess_minidump_prerequisites,
    build_capture_readiness,
    cdb_status,
    check_full_dump,
    clear_cdb_path_cache,
    collect_kernel_minidumps,
    enable_memory_dumps_or_report_status,
    enrich_windbg_analysis,
    find_cdb,
    get_crash_dump_settings,
    get_cdb_version,
    get_dump_config,
    get_minidump_search_directories,
    install_cdb,
    launch_latest_dump_in_windbg,
    list_dumps,
    list_dumps_from_paths,
    merge_recovered_kernel_dumps,
    minidump_capture_action_step,
    parse_report_wer,
    prompt_install_cdb,
    reconcile_wer_dumpfile_gaps,
    repair_local_cdb_engine_if_needed,
    scan_for_cdb_and_report,
    should_prompt_cdb_online_install,
    update_cdb,
    _cdb_engine_usable,
    _cdb_search_arch_dirs,
    _check_and_offer_cdb_update,
    _expand_windows_path,
    _find_windbg_app_engine_dir,
    _get_local_cdb_path,
    _get_tool_dir,
    _is_online,
    _module_from_wer_bucket,
    _wer_report_module_hint,
)

from bsod_crash_report import (
    FIX_BOOT_RECOVERY,
    FIX_CPU_PLATFORM,
    FIX_NAMED_DRIVER,
    FIX_UNCERTAIN,
    analyze_recent_minidumps,
    boot_events_near_crash,
    build_boot_failure_playbook_steps,
    build_crash_confidence_summary,
    build_crash_fix_plan,
    build_display_model,
    build_driver_update_options,
    build_event_log_coverage_summary,
    build_hardware_enrichment_bundle,
    build_incident_timeline,
    build_platform_update_options,
    build_report_derivations,
    crash_synthetic_device_key,
    derive_report_fix_focus,
    device_inventory_for_matching,
    enrich_bios_driver_info,
    find_culprit_devices,
    format_minidump_summary_line,
    format_output,
    format_output_from_fmt_args,
    get_bugcheck_info,
    get_culprit_device_driver_info,
    get_wmi_monitor_edid_by_device_id,
    has_crash_faulting_driver,
    is_crash_synthetic_device_key,
    is_kernel_shim_fault_module,
    is_platform_chipset_device_key,
    lookup_inventory_row,
    merge_verification_action_steps,
    sanitize_action_plan_steps,
    minidump_without_bugcheck_gap,
    newest_minidump_analysis,
    platform_chipset_crash_attention,
    refresh_model_culprit_fields,
    resolve_crash_code,
    resolve_crash_culprit_context,
    run_driver_update_option,
    _AMD_CHIPSET_DRIVER_URL,
    _ANALYSIS_TASK_LABELS,
    _analysis_gap_message,
    _culprit_info_row_is_placeholder,
    _dump_matches_recent_events,
    _find_pnp_entity_by_device_name,
    _friendly_driver_label,
    _INCIDENT_WHEA_WINDOW_MIN,
    _match_event_to_crash,
    _oem_model_support_url,
    _parse_event_time,
    _pc_support_drivers_url,
    _quick_answer_lines,
    _RELIABILITY_NEAR_CRASH_WINDOW_MIN,
    _system_ctx_with_service_tag,
    _THERMAL_NEAR_CRASH_WINDOW_MIN,
    _usable_bugcheck_events,
    _WHEA_NEAR_CRASH_WINDOW_MIN,
)

from analyzer_gather import gather_firmware_inventory_for_gui, gather_report_data
from analyzer_hardware import gather_hardware_profile


def request_admin_elevation() -> bool:
    """If not running as admin, prompt to relaunch elevated. Returns True if already admin or relaunched."""
    if sys.platform != "win32":
        return True
    try:
        if ctypes.windll.shell32.IsUserAnAdmin():
            return True
    except (OSError, AttributeError):
        pass
    # Relaunch as admin
    try:
        exe = sys.executable if getattr(sys, "frozen", False) else sys.argv[0]
        params = " ".join(f'"{x}"' for x in sys.argv[1:]) if len(sys.argv) > 1 else ""
        work_dir = str(Path(exe).resolve().parent) if exe else None
        ret = ctypes.windll.shell32.ShellExecuteW(
            None, "runas", exe, params, work_dir, 1
        )
        if ret > 32:
            console_print("Relaunching as Administrator — approve the UAC prompt…")
            sys.exit(0)
    except (OSError, AttributeError):
        pass
    console_print("This tool works best with Administrator rights.")
    console_print("Right-click BSODAnalyzer.exe > Run as administrator")
    console_print("Continuing with limited access...\n")
    return False


def is_user_admin() -> bool:
    """True when the current process has Administrator elevation."""
    if sys.platform != "win32":
        return True
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False






def run_analysis(report_width: int | None = None, dual_report: bool = False, progress_cb=None) -> tuple:
    """
    Run full analysis (event logs, dumps, BIOS/drivers, recommendations).
    report_width: wrap width in characters (default 68). Pass display width in chars to match window.
    dual_report: if True, return (simple_report, needs_config, full_report) for GUI toggle.
    progress_cb(percent, message): optional callback for overall analysis progress (used by the GUI).
    Returns (report_text, needs_config) or (simple_report, needs_config, full_report).
    """
    fmt_args, needs_config = gather_report_data(progress_cb=progress_cb)
    full_output = format_output(*fmt_args, report_width=report_width, include_technical_details=True)
    if dual_report:
        simple_output = format_output(*fmt_args, report_width=report_width, include_technical_details=False)
        return simple_output, needs_config, full_output
    return full_output, needs_config












def main() -> None:
    configure_console_encoding()
    if sys.platform == "win32":
        request_admin_elevation()
    console_print("=" * 50)
    console_print("  BSOD Analyzer v" + VERSION)
    console_print("=" * 50)
    console_print("Scanning for Debugging Tools...")
    cdb_found = scan_for_cdb_and_report()

    # CDB update/install prompts BEFORE scanning - user provides input first
    if cdb_found and _is_online():
        _check_and_offer_cdb_update()
    elif not cdb_found:
        prompt_install_cdb()

    console_print()
    console_print("Analyzing event logs and dump files...")
    console_print()

    output, needs_config = run_analysis()
    console_print(output)

    # Offer to save report to file
    try:
        if sys.stdin.isatty():
            r = input("\nSave report to file? (Y/N): ").strip().upper()
            if r == "Y":
                default_name = f"BSODAnalyzer_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
                path = os.path.join(_get_tool_dir(), default_name)
                ok, msg = export_report_to_file(path, output)
                console_print(f"  {msg}" if ok else f"  Error: {msg}")
    except (EOFError, OSError):
        pass

    # Offer to configure memory dumps for future crashes (when disabled)
    if needs_config:
        try:
            if sys.stdin.isatty():
                prompt = (
                    "\nWindows memory dumps have not been enabled in the Windows registry, having "
                    "a memory dump performed when your system crashes will help with discovering "
                    "the root cause of your system instability, would you like to enable this "
                    "feature? (Y/N): "
                )
                r = input(prompt).strip().upper()
                if r in ("Y", "YES"):
                    msg, _changed = enable_memory_dumps_or_report_status(1)
                    console_print(f"  {msg}")
        except (EOFError, OSError):
            pass

    if getattr(sys, "frozen", False):
        pause_before_exit()



def probe_cdb_path() -> int:
    """Print resolved CDB path and exit (used by post-build smoke tests)."""
    configure_console_encoding()
    clear_cdb_path_cache()
    path = find_cdb()
    if not path or not os.path.isfile(path):
        console_print("CDB_NOT_FOUND")
        return 1
    console_print(path)
    return 0


def probe_mscatalog_module() -> int:
    """Print resolved MSCatalogLTS module path and exit (portable build smoke)."""
    configure_console_encoding()
    try:
        import catalog_ps_module as cps
    except ImportError:
        console_print("MSCATALOG_MODULE_NOT_FOUND")
        return 1
    ok, msg = cps.probe_mscatalog_module()
    if not ok:
        console_print("MSCATALOG_MODULE_NOT_FOUND")
        if msg:
            console_print(msg)
        return 1
    console_print(msg)
    return 0


def launch_gui() -> None:
    """Launch the PySide6 GUI."""
    from gui_qt_bootstrap import prepare_interactive_gui

    prepare_interactive_gui()
    import bsod_gui_qt

    bsod_gui_qt.run_gui_qt()


if __name__ == "__main__":
    args_lower = [a.strip().lower() for a in sys.argv[1:]]
    if any(a in ("--probe-cdb",) for a in args_lower):
        if getattr(sys, "frozen", False):
            from bsod_runtime import ensure_cli_console

            ensure_cli_console()
        sys.exit(probe_cdb_path())
    if any(a in ("--probe-mscatalog",) for a in args_lower):
        if getattr(sys, "frozen", False):
            from bsod_runtime import ensure_cli_console

            ensure_cli_console()
        sys.exit(probe_mscatalog_module())
    use_cli = any(a in ("--cli", "-c", "/cli") for a in args_lower)
    use_gui = any(a in ("--gui", "-g", "/gui") for a in args_lower)
    if getattr(sys, "frozen", False):
        if use_cli:
            ensure_cli_console()
            configure_console_encoding()
            main()
        else:
            if sys.platform == "win32":
                request_admin_elevation()
            launch_gui()
    else:
        if use_gui:
            if sys.platform == "win32":
                request_admin_elevation()
            launch_gui()
        else:
            main()
