"""Text report formatting and GUI display model (extracted from bsod_crash_report)."""

from __future__ import annotations

from datetime import datetime

import log_read_windows as lrw

from bsod_hardware_wmi import _parse_json_date
from bsod_events import compute_crash_timeline
from bsod_minidump import MINIDUMP_DIR, assess_minidump_prerequisites, build_capture_readiness
from crash_report_culprit import (
    POSSIBLE_DRIVERS,
    build_culprit_system_callout,
    device_inventory_for_matching,
    find_culprit_devices,
    has_crash_faulting_driver,
    lookup_inventory_row,
    resolve_crash_culprit_context,
    _filter_possible_drivers_list,
    _infer_driver_vendor,
)
from crash_report_events import (
    decode_exception_code as _decode_exception_code,
    group_events_by_incident as _group_events_by_incident,
    parse_p1 as _parse_p1,
)
from crash_report_fix_plan import (
    _describe_action_plan_link_basis,
    _merge_update_options,
    _needs_platform_driver_links,
    build_boot_failure_playbook_steps,
    build_crash_fix_plan,
    build_platform_update_options,
    derive_report_fix_focus,
)
from crash_report_timeline import (
    _dump_matches_event_time,
    _dump_matches_recent_events,
    _usable_bugcheck_events,
    _verified_stop_for_incident,
    build_incident_timeline,
    resolve_crash_code,
)


def _bc(name: str):
    """Lazy bsod_crash_report lookup — avoids import cycles during module load."""
    import bsod_crash_report as bc

    return getattr(bc, name)


_REPORT_WIDTH = 68

_MAX_LINE_LEN = 2 + _REPORT_WIDTH  # 70

def _wrap_text(text: str, max_len: int, indent: str) -> list[str]:
    """Word-wrap text so each line is at most max_len chars. Each line starts with indent (included in max_len)."""
    if not text or not text.strip():
        return []
    words = text.split()
    lines = []
    current = indent
    for w in words:
        candidate = (current + " " + w) if current != indent else (current + w)
        if len(candidate) <= max_len:
            current = candidate
        else:
            if current.strip():
                lines.append(current)
            current = indent + w
    if current.strip():
        lines.append(current)
    return lines

def _wrap_with_prefix(prefix: str, body: str, max_len: int = _MAX_LINE_LEN, cont_indent: str = "  ") -> list[str]:
    """First line is prefix + first part of body; continuation lines are cont_indent + part. All lines <= max_len."""
    if not body or not body.strip():
        return [prefix] if prefix.strip() else []
    words = body.split()
    lines = []
    current = prefix
    for w in words:
        candidate = (current + " " + w) if current != prefix else (current + w)
        if len(candidate) <= max_len:
            current = candidate
        else:
            if current.strip():
                lines.append(current)
            current = cont_indent + w
    if current.strip():
        lines.append(current)
    return lines

def _section_header(title: str, width: int = _REPORT_WIDTH) -> list[str]:
    """Return [separator, title, separator] so the report flow is obvious (Section 1, 2, 3...)."""
    sep = "  " + "=" * width
    return [sep, "  " + title, sep]


def format_minidump_summary_line(dump: dict) -> str:
    """
    One minidump as 'name  (time, N MB)', omitting fields the dump entry does not carry.

    A partial entry must not abort report generation — a missing size is far less
    important than the rest of the report reaching the user.
    """
    name = str(dump.get("name") or dump.get("path") or "(unnamed dump)")
    detail = [str(dump[k]) for k in ("time",) if dump.get(k)]
    size = dump.get("size_mb")
    if size not in (None, ""):
        detail.append(f"{size} MB")
    return f"{name}  ({', '.join(detail)})" if detail else name

def _quick_answer_lines(events: list, windbg_analysis: dict | None, whea_events: list,
                        thermal_events: list, max_line_len: int = _MAX_LINE_LEN,
                        *, fix_plan: dict | None = None,
                        driver_verification: dict | None = None,
                        crash_confidence: dict | None = None,
                        plain_english_override: str | None = None,
                        boot_recovery_events: list | None = None,
                        repair_narrative: dict | None = None) -> tuple[list[str], str, str]:
    """Build Quick Answer lines and return (lines, root_cause_one_line, fix_one_line)."""
    if repair_narrative:
        try:
            import driver_verification as drvver

            lines = drvver.format_repair_narrative_quick_answer(repair_narrative)
            wf = repair_narrative.get("what_failed") or {}
            root_cause = wf.get("summary") or repair_narrative.get("what_happened") or ""
            steps = repair_narrative.get("action_steps") or []
            fix = steps[0] if steps else "See Section 2 (Action Plan)."
            return lines, root_cause, fix
        except Exception:
            pass  # repair narrative optional; fall through to generic quick answer

    lines = []
    root_cause = ""
    fix = ""
    boot_recovery_events = boot_recovery_events or []
    code_val, stop_name, stop_desc, has_event_bugcheck = resolve_crash_code(
        events, windbg_analysis
    )
    bugchecks = _usable_bugcheck_events(events, windbg_analysis)
    other = [e for e in events if e.get("type") in ("KernelPower", "UnexpectedShutdown")]
    dump_matches = _dump_matches_recent_events(windbg_analysis, events)
    latest_incident = _group_events_by_incident(events)[0] if events else []
    _lc, _ln, _ld, latest_verified = _verified_stop_for_incident(
        latest_incident, windbg_analysis, events=events
    ) if latest_incident else (None, "", "", False)
    if (bugchecks or code_val is not None) and latest_verified:
        if bugchecks:
            evt = bugchecks[0]
            time_str = evt.get("time", "?")
            lines.append(f"  When (event log): {time_str}")
        elif windbg_analysis:
            time_str = windbg_analysis.get("dump_time") or "?"
            lines.append(f"  When (minidump): {time_str}")
        else:
            time_str = "?"
        if windbg_analysis and windbg_analysis.get("dump_time"):
            dump_t = windbg_analysis["dump_time"]
            if bugchecks and not _dump_matches_event_time(windbg_analysis, time_str):
                lines.append(f"  Latest minidump: {dump_t} (older than this event)")
        if stop_name:
            lines.append(f"  Stop code: {stop_name}")
        if windbg_analysis and windbg_analysis.get("bugcheck_str"):
            lines.append(f"  WinDbg stop code: {windbg_analysis['bugcheck_str']}")
        lines.append("")
        root_cause = stop_desc or stop_name or "See Section 4 below."
        drv = None
        if windbg_analysis and dump_matches:
            drv = windbg_analysis.get("faulting_driver") or windbg_analysis.get("kernel_stack_top")
        if drv:
            drv_base = (drv or "").lower().replace(".sys", "").replace(".dll", "").replace(".exe", "").strip()
            if drv_base in _bc("GENERIC_FAULT_MODULE_DEVICE"):
                device, action = _bc("GENERIC_FAULT_MODULE_DEVICE")[drv_base]
                root_cause = f"Hardware error (WHEA). The dump points to '{drv}' — this is the {device}, not a driver. The problem is likely CPU microcode, BIOS, chipset, or cooling."
                fix = f"{action}. See Section 2 (Action Plan) and Section 3 (Your system) for BIOS and driver details."
            else:
                if drv.lower().replace(".exe", "").replace(".sys", "") == "ntoskrnl":
                    root_cause = (
                        "Kernel fault (ntoskrnl.exe on the stack). This usually means a "
                        "third-party driver or hardware issue during boot or runtime — not a corrupt Windows kernel."
                    )
                    fix = "Update BIOS/chipset, GPU, storage, and network drivers; see Action Plan (Section 2)."
                else:
                    root_cause = f"Hardware/driver issue. Faulting module from dump: {drv}."
                    fix = f"Update or rollback: {drv} (and update BIOS/chipset as in Action Plan)."
        else:
            fix = "Update BIOS/UEFI and chipset drivers; run system checks in Action Plan (Section 2)."
        if fix_plan and fix_plan.get("steps"):
            fix = fix_plan["steps"][0]
        plain = plain_english_override or _bc("_build_plain_english_summary")(
            windbg_analysis, code_val, stop_name, stop_desc
        )
        lines.append("  IN PLAIN ENGLISH:")
        for ln in _wrap_text(plain, max_line_len, "    "):
            lines.append(ln)
        lines.append("")
        conf = _bc("_analysis_confidence_label")(
            windbg_analysis, has_event_bugcheck or code_val is not None
        )
        lines.append("  CONFIDENCE:")
        for ln in _wrap_text(conf, max_line_len, "    "):
            lines.append(ln)
        lines.append("")
        if windbg_analysis and windbg_analysis.get("dumps_analyzed", 0) > 0 and dump_matches:
            da = windbg_analysis["dumps_analyzed"]
            lines.append(f"  WinDbg analysis: {da} minidump(s) analyzed.")
            if windbg_analysis.get("failure_bucket_id"):
                lines.append(f"  Failure bucket: {windbg_analysis['failure_bucket_id']}")
            if windbg_analysis.get("process_name"):
                lines.append(f"  Process at crash: {windbg_analysis['process_name']}")
            if windbg_analysis.get("stack_frames"):
                lines.append(f"  Call stack: {' → '.join(windbg_analysis['stack_frames'][:3])}")
            lines.append("")
        lines.append("  ROOT CAUSE:")
        for ln in _wrap_text(root_cause, max_line_len, "    "):
            lines.append(ln)
        lines.append("")
        lines.append("  PRIMARY FIX:")
        for ln in _wrap_text(fix, max_line_len, "    "):
            lines.append(ln)
    elif other:
        evt = other[0]
        lines.append(f"  When (event log): {evt.get('time', '?')}")
        if boot_recovery_events:
            br = boot_recovery_events[0]
            subtype = br.get("subtype") or "BootRecovery"
            lines.append(
                f"  Boot/recovery signal: {subtype} at {br.get('time', '?')}"
            )
        if windbg_analysis and windbg_analysis.get("dump_time") and not dump_matches:
            lines.append(
                f"  Latest minidump: {windbg_analysis['dump_time']} "
                "(not from this shutdown — stop code not applied)"
            )
        lines.append("  No stop code was recorded (unexpected shutdown).")
        if boot_recovery_events:
            lines.append(
                "  Boot/recovery events suggest a failed or interrupted boot "
                "(chipset, storage, or firmware — not a logged BSOD stop code)."
            )
        lines.append("")
        conf = crash_confidence or {}
        for ln in conf.get("lines") or []:
            for wrapped in _wrap_text(ln.strip(), max_line_len, "  "):
                lines.append(wrapped)
        if conf.get("what_would_change"):
            lines.append("")
        attribution = list(
            ((driver_verification or {}).get("attribution") or {}).get("lines") or []
        )
        if not attribution and driver_verification:
            attribution = list(driver_verification.get("lines") or [])[:6]
        if boot_recovery_events:
            root_cause = (
                "Windows reported an unexpected shutdown or boot recovery activity. "
                "This often happens when cold boot fails before a minidump is written."
            )
            fix = (
                "Check Section 5a (Boot & recovery), update BIOS/chipset and storage/GPU drivers, "
                "then run Action Plan (Section 2)."
            )
        else:
            root_cause = "Power loss or crash before Windows could log the error."
            fix = "Check power supply and connections; run Action Plan (Section 2) to update drivers and run system checks."
        ver_steps = []
        if driver_verification:
            try:
                import driver_verification as drvver

                ver_steps = drvver.verification_action_plan_steps(driver_verification)
            except Exception:
                ver_steps = driver_verification.get("action_plan_steps") or []
        if ver_steps:
            fix = ver_steps[0]
        for ln in attribution:
            for wrapped in _wrap_text(ln.strip(), max_line_len, "  "):
                lines.append(wrapped)
        if attribution:
            lines.append("")
        lines.append("  ROOT CAUSE:")
        for ln in _wrap_text(root_cause, max_line_len, "    "):
            lines.append(ln)
        lines.append("")
        lines.append("  PRIMARY FIX:")
        for ln in _wrap_text(fix, max_line_len, "    "):
            lines.append(ln)
    else:
        lines.append("  No kernel crash events found in event logs.")
        if events:
            lines.append("  Run as Administrator for full event log access.")
        root_cause = "None detected."
        fix = "Run as Administrator and re-scan; if crashes continue, follow general Action Plan."
        lines.append("")
        lines.append("  ROOT CAUSE:")
        for ln in _wrap_text(root_cause, max_line_len, "    "):
            lines.append(ln)
        lines.append("")
        lines.append("  PRIMARY FIX:")
        for ln in _wrap_text(fix, max_line_len, "    "):
            lines.append(ln)
    return lines, root_cause, fix

def _system_context_summary(ctx: dict) -> str:
    """One-line summary of detected hardware so the user sees recommendations are tailored."""
    parts = []
    hw = ctx.get("hardware_vendors", {})
    
    # Filter out generic/virtual vendors for display purposes
    GENERIC_VENDORS = {"microsoft", "generic", "standard", "virtual", "windows"}
    
    def filter_vendors(vendors: set) -> set:
        """Remove generic vendors. Returns empty set if only generic vendors."""
        return vendors - GENERIC_VENDORS
    
    def format_vendors(vendors: set, max_show: int = 2) -> str:
        """Format vendor set as capitalized string, limit to max_show."""
        vendors = filter_vendors(vendors)
        if not vendors:
            return ""
        sorted_v = sorted(v.capitalize() for v in vendors)
        if len(sorted_v) > max_show:
            return "/".join(sorted_v[:max_show]) + f" +{len(sorted_v) - max_show}"
        return "/".join(sorted_v)
    
    # Storage
    if ctx.get("has_nvme") and not ctx.get("has_sata"):
        parts.append("NVMe (no SATA)")
    elif ctx.get("has_sata") and not ctx.get("has_nvme"):
        parts.append("SATA storage")
    elif ctx.get("has_sata") and ctx.get("has_nvme"):
        parts.append("NVMe + SATA")
    
    # GPU (show all if multiple)
    gpu_vendors = ctx.get("gpu_vendors_present", set())
    if gpu_vendors:
        gpu_names = []
        if "nvidia" in gpu_vendors:
            gpu_names.append("NVIDIA")
        if "amd" in gpu_vendors:
            gpu_names.append("AMD")
        if "intel" in gpu_vendors:
            gpu_names.append("Intel")
        if gpu_names:
            parts.append(" + ".join(gpu_names) + " GPU")
    elif ctx.get("gpu_vendor"):
        parts.append(f"{ctx['gpu_vendor'].upper()} GPU")
    
    # Chipset
    if ctx.get("has_amd_chipset"):
        parts.append("AMD chipset")
    elif ctx.get("has_intel_chipset"):
        parts.append("Intel chipset")
    
    # Network (filter generic vendors)
    net_vendors = filter_vendors(hw.get("network", set()))
    if net_vendors:
        parts.append(f"{format_vendors(net_vendors)} network")
    
    # Audio (filter out HDMI audio from GPU and generic for cleaner summary)
    audio_vendors = filter_vendors(hw.get("audio", set()) - {"nvidia", "amd", "intel"})
    if audio_vendors:
        parts.append(f"{format_vendors(audio_vendors)} audio")
    
    # Bluetooth (filter generic)
    bt_vendors = filter_vendors(hw.get("bluetooth", set()))
    if bt_vendors:
        parts.append(f"{format_vendors(bt_vendors)} BT")
    
    # Webcam (filter generic)
    webcam_vendors = filter_vendors(hw.get("webcam", set()))
    if webcam_vendors:
        parts.append(f"{format_vendors(webcam_vendors)} webcam")
    
    # Fingerprint (filter generic)
    fp_vendors = filter_vendors(hw.get("fingerprint", set()))
    if fp_vendors:
        parts.append(f"{format_vendors(fp_vendors)} fingerprint")
    
    # Card reader (filter generic)
    cr_vendors = filter_vendors(hw.get("card_reader", set()))
    if cr_vendors:
        parts.append(f"{format_vendors(cr_vendors)} card reader")
    
    # Thunderbolt
    tb_vendors = hw.get("thunderbolt", set())
    if tb_vendors:
        parts.append("Thunderbolt")
    
    return "; ".join(parts) if parts else "Hardware detected"

def format_output(events: list, kernel_dumps: list, full_dump: dict | None, app_dumps: list,
                  windbg_analysis: dict | None, whea_events: list, thermal_events: list,
                  dump_config: str, dump_val: int | None, needs_config: bool,
                  logged_in_user: str = "", user_crashdumps_path: str = "",
                  app_crash_events: list | None = None, bios_driver_info: dict | None = None,
                  system_ctx: dict | None = None, devices_with_driver_problems: list | None = None,
                  devices_with_generic_driver: list | None = None,
                  reliability_ctx: dict | None = None,
                  report_width: int | None = None,
                  include_technical_details: bool = True,
                  analysis_elapsed_ms: int | None = None) -> str:
    """Build human-readable output. Set include_technical_details=False for novice/simple view (GUI default)."""
    if report_width is None or report_width < 20:
        report_width = _REPORT_WIDTH
    max_len = 2 + report_width
    if app_crash_events is None:
        app_crash_events = []
    if bios_driver_info is None:
        bios_driver_info = {}
    if system_ctx is None:
        system_ctx = {"present_drivers": set(), "has_sata": True, "has_nvme": True, "gpu_vendor": None}
    if devices_with_driver_problems is None:
        devices_with_driver_problems = []
    if devices_with_generic_driver is None:
        devices_with_generic_driver = []
    if reliability_ctx is None:
        reliability_ctx = {"livekernel": [], "wer_errors": [], "stability_index": None}
    fmt_args = (
        events, kernel_dumps, full_dump, app_dumps,
        windbg_analysis, whea_events, thermal_events,
        dump_config, dump_val, needs_config,
        logged_in_user, user_crashdumps_path,
        app_crash_events, bios_driver_info,
        system_ctx, devices_with_driver_problems,
        devices_with_generic_driver, reliability_ctx,
    )
    deriv = build_report_derivations(fmt_args)
    lines = []
    crash_times = [e["time"] for e in events if e.get("time")]

    # ---- Title (same width as section separators so borders line up) ----
    _sep = "  " + "=" * report_width
    lines.append(_sep)
    lines.append("  WINDOWS CRASH & BSOD ANALYZER — Report")
    for ln in _wrap_text("Read Section 1 first (Quick Answer), then Section 2 (Action Plan), then Section 3 (Your system — what to update).", max_len, "  "):
        lines.append(ln)
    lines.append(_sep)
    if logged_in_user:
        lines.append(f"  User: {logged_in_user}")
        if user_crashdumps_path:
            lines.append(f"  Crash dumps path: {user_crashdumps_path}")
    summary = _system_context_summary(system_ctx)
    for ln in _wrap_with_prefix("  Detected on this system: ", summary, max_len, "  "):
        lines.append(ln)
    if analysis_elapsed_ms is not None and analysis_elapsed_ms >= 0:
        try:
            import catalog_export as cexp

            human = cexp.format_elapsed_ms(analysis_elapsed_ms)
            lines.append(f"  Run Analysis duration: {human or analysis_elapsed_ms}")
        except ImportError:
            lines.append(f"  Run Analysis duration: {analysis_elapsed_ms} ms")
    lines.append("")

    # ---- 1. QUICK ANSWER (root cause + primary fix at top) ----
    for x in _section_header("1. QUICK ANSWER — What crashed and what to do", report_width):
        lines.append(x)
    lines.append("")
    quick_lines, _rc, _fix = _quick_answer_lines(
        events, windbg_analysis, whea_events, thermal_events, max_len,
        fix_plan=deriv.get("fix_plan"),
        driver_verification=deriv.get("driver_verification"),
        crash_confidence=deriv.get("crash_confidence"),
        plain_english_override=deriv.get("plain_english"),
        boot_recovery_events=reliability_ctx.get("boot_recovery") or [],
        repair_narrative=(deriv.get("driver_verification") or {}).get("repair_narrative"),
    )
    for ln in quick_lines:
        if ln == "":
            lines.append("")
        elif ln.startswith("  "):
            lines.append(ln)
        else:
            lines.append("  " + ln)
    lines.append("")

    # ---- 2. ACTION PLAN — FIXES (numbered steps) ----
    recs = deriv["recommendations"]
    for x in _section_header("2. ACTION PLAN — Fixes (do these in order)", report_width):
        lines.append(x)
    lines.append("")
    lines.append("  To fix or reduce crashes, do the following:")
    lines.append("")
    step = 0
    for r in recs:
        r_clean = r.strip()
        if r_clean.startswith(("1)", "2)", "3)", "4)")):
            for ln in _wrap_with_prefix("      ", r_clean, max_len, "         "):
                lines.append(ln)
        else:
            step += 1
            prefix = f"  {step}. "
            cont_indent = "     "
            for ln in _wrap_with_prefix(prefix, r_clean, max_len, cont_indent):
                lines.append(ln)
    lines.append("")

    # ---- 3. YOUR SYSTEM (BIOS & drivers) — early so user sees what to update ----
    for x in _section_header("3. YOUR SYSTEM — BIOS / Firmware and drivers", report_width):
        lines.append(x)
    lines.append("")
    if devices_with_driver_problems:
        for ln in _wrap_text("Devices with missing or problematic drivers (install/update these):", max_len, "  "):
            lines.append(ln)
        lines.append("  " + "-" * report_width)
        for dev in devices_with_driver_problems[:20]:
            lines.append(f"  • {dev.get('name', '?')}")
            err_line = f"{dev.get('error_meaning', '')} (Code {dev.get('error_code', '')})"
            for ln in _wrap_text(err_line, max_len, "    "):
                lines.append(ln)
        for ln in _wrap_text("FIX: Open Device Manager, find these devices, right-click > Update driver (or install driver from manufacturer).", max_len, "  "):
            lines.append(ln)
        lines.append("")
    if devices_with_generic_driver:
        for ln in _wrap_text("Devices using a generic driver (may need vendor driver for best stability):", max_len, "  "):
            lines.append(ln)
        lines.append("  " + "-" * report_width)
        for dev in devices_with_generic_driver[:15]:
            lines.append(f"  • {dev.get('name', '?')}")
        if len(devices_with_generic_driver) > 15:
            lines.append(f"  ... and {len(devices_with_generic_driver) - 15} more.")
        for ln in _wrap_text("FIX: These devices work but may run better with a vendor driver. Check PC/motherboard vendor support site or Device Manager > Update driver.", max_len, "  "):
            lines.append(ln)
        lines.append("")
    if bios_driver_info:
        bios = bios_driver_info.get("bios") or {}
        if bios and (bios.get("manufacturer") or bios.get("version")):
            lines.append(f"  BIOS Manufacturer: {bios.get('manufacturer', '')}")
            lines.append(f"  BIOS Version: {bios.get('version', '')}")
            lines.append(f"  BIOS Date: {_parse_json_date(bios.get('date', ''))}")
            lines.append("")
        drivers = bios_driver_info.get("drivers") or []
        all_drivers = bios_driver_info.get("all_drivers") or []
        if drivers:
            lines.append(f"  Common devices ({len(drivers)}) — graphics, storage, network, audio, input:")
            for d in drivers:
                date_str = _parse_json_date(d.get("date", ""))
                drv_line = f"{d.get('name', '')}  Version: {d.get('version', '')}  Date: {date_str}"
                for ln in _wrap_with_prefix("  • ", drv_line, max_len, "    "):
                    lines.append(ln)
            lines.append("")
        if all_drivers and include_technical_details:
            lines.append(f"  All installed devices ({len(all_drivers)}):")
            for d in all_drivers:
                date_str = _parse_json_date(d.get("date", ""))
                cls = d.get("device_class", "")
                cls_str = f" [{cls}]" if cls else ""
                drv_line = f"{d.get('name', '')}{cls_str}  Version: {d.get('version', '')}  Date: {date_str}"
                for ln in _wrap_with_prefix("  • ", drv_line, max_len, "    "):
                    lines.append(ln)
            lines.append("")
        elif all_drivers and not include_technical_details:
            for ln in _wrap_text(
                f"Full driver inventory ({len(all_drivers)} devices) omitted in summary report — "
                "use Export full report or the Drivers tab.",
                max_len,
                "  ",
            ):
                lines.append(ln)
            lines.append("")
    else:
        lines.append("  No BIOS/driver data gathered.")
        lines.append("")
    drv_ver = deriv.get("driver_verification") or {}
    if drv_ver.get("has_suspects"):
        for x in _section_header(
            "3b. DRIVER VERIFICATION — Crash-linked install checks", report_width
        ):
            lines.append(x)
        lines.append("")
        lines.append(
            "  Local checks on devices tied to crash evidence (no internet required)."
        )
        lines.append("")
        for ln in drv_ver.get("lines") or []:
            if ln.strip():
                for wrapped in _wrap_text(ln.strip(), max_len, "  "):
                    lines.append(wrapped)
            else:
                lines.append("")
        gated = int(drv_ver.get("catalog_gated_count") or 0)
        if gated:
            for ln in _wrap_text(
                f"Catalog: {gated} suspect(s) flagged for Drivers tab → Check "
                "(crash-linked rows are pre-marked).",
                max_len,
                "  ",
            ):
                lines.append(ln)
        lines.append("")
    lines.append("")
    lines.append("")

    # ---- 4-6 are technical sections, hidden in the simple/novice GUI view ----
    incidents = _group_events_by_incident(events, window_minutes=2) if events else []
    if include_technical_details:
        # ---- 4. CRASH INCIDENTS (each with ROOT CAUSE + FIX) ----
        for x in _section_header("4. CRASH INCIDENTS — Details per crash", report_width):
            lines.append(x)
        lines.append("")
        for ln in _wrap_text(
            "Log read windows (newest N records per source — not a calendar cutoff):",
            max_len,
            "  ",
        ):
            lines.append(ln)
        for wl in (deriv.get("log_coverage") or {}).get("read_window_lines") or lrw.read_windows_detail_lines():
            for ln in _wrap_text(wl, max_len, "    "):
                lines.append(ln)
        lines.append("")
        itl = deriv.get("incident_timeline") or {}
        itl_entries = itl.get("entries") or []
        if itl_entries:
            lines.append("  Incident timeline (newest first):")
            for ent in itl_entries[:10]:
                rel = ent.get("relevance") or ("historical" if ent.get("historical") else "current")
                tag = " [Historical]" if rel == "historical" else ""
                row = (
                    f"{ent.get('time', '?')}  {ent.get('label', '')}{tag}"
                )
                for ln in _wrap_with_prefix("  • ", row.strip(), max_len, "    "):
                    lines.append(ln)
                detail = (ent.get("detail") or "").strip()
                if detail:
                    for ln in _wrap_text(detail, max_len, "      "):
                        lines.append(ln)
            if itl.get("stale_dump_note"):
                for ln in _wrap_text(itl["stale_dump_note"], max_len, "  "):
                    lines.append(ln)
            lines.append("")
        if incidents:
            for idx, group in enumerate(incidents[:8]):
                evt = next((e for e in group if e.get("type") == "BugCheck"), group[0])
                evt = next((e for e in group if e.get("type") == "KernelPower" and evt.get("type") != "BugCheck"), evt)
                time_str = evt.get("time", "?")
                types_in_group = ", ".join(sorted(set(e.get("type", "") for e in group)))
                hist_tag = " [Historical]" if idx > 0 else " [Current — latest incident]"
                lines.append(f"  --- Incident {idx + 1} ({time_str}){hist_tag} ---")
                lines.append(f"  Events in this crash: {types_in_group}")
                cause_text = ""
                icode, iname, idesc, iverified = _verified_stop_for_incident(
                    group, windbg_analysis, events=events
                )
                if iverified and (icode is not None or iname):
                    lines.append(f"  Stop code: {iname or icode}")
                    cause_text = idesc or iname or ""
                elif evt.get("note"):
                    lines.append(f"  Note: {evt['note']}")
                    cause_text = evt["note"]
                incident_evt = dict(evt)
                if icode is not None and iverified:
                    incident_evt["code"] = f"0x{icode:08X}"
                elif not iverified:
                    incident_evt["code"] = "N/A"
                definitive = _bc("_build_definitive_cause")(
                    incident_evt, windbg_analysis, whea_events, thermal_events, crash_times,
                    is_most_recent=(idx == 0), reliability_ctx=reliability_ctx,
                )
                if definitive:
                    cause_parts = [d.strip() for d in definitive if d.strip()]
                    if cause_parts:
                        cause_text = cause_parts[0] if not cause_text else cause_text + " " + cause_parts[0]
                lines.append("  ROOT CAUSE:")
                for ln in _wrap_text(cause_text or "Unexpected shutdown; no stop code.", max_len, "    "):
                    lines.append(ln)
                lines.append("  FIX:")
                added = False
                for d in (definitive or []):
                    line = d.strip()
                    if not line:
                        continue
                    if "Action:" in line:
                        bullet = "    • " + line.replace("Action:", "").strip()
                        for ln in _wrap_with_prefix("    • ", line.replace("Action:", "").strip(), max_len, "      "):
                            lines.append(ln)
                        added = True
                    elif "Possible specific" in line:
                        for ln in _wrap_with_prefix("    • ", line.replace("Possible specific drivers:", "Update:").strip(), max_len, "      "):
                            lines.append(ln)
                        added = True
                    elif "WHEA 0x124:" in line or "Often" in line:
                        for ln in _wrap_with_prefix("    • ", line, max_len, "      "):
                            lines.append(ln)
                        added = True
                if not added:
                    lines.append("    • Do Section 2 (Action Plan) above.")
                lines.append("")
        else:
            for ln in _wrap_text("No crash events found. Run as Administrator for full event log access.", max_len, "  "):
                lines.append(ln)
            lines.append("")
        lines.append("")

        # ---- 5. APPLICATION CRASHES (Event 1000) ----
        for x in _section_header("5. APPLICATION CRASHES — App errors (not BSOD)", report_width):
            lines.append(x)
        lines.append("")
        if app_crash_events:
            lines.append("  These are program crashes; exception meaning is decoded.")
            lines.append("")
            for evt in app_crash_events[:15]:
                app = evt.get("application", "?")
                mod = evt.get("module", "")
                exc = evt.get("exception_code", "")
                exc_meaning = _decode_exception_code(exc) if exc else ""
                body = f"{evt.get('time', '?')}  {app}  | Module: {mod}"
                if exc_meaning:
                    body += f"  | {exc_meaning}"
                elif exc:
                    body += f"  | Exception: {exc}"
                for ln in _wrap_with_prefix("  • ", body, max_len, "  "):
                    lines.append(ln)
            lines.append("")
            for ln in _wrap_text("FIX for app crashes: Update or reinstall the crashing app; check for .NET/VC++ runtimes.", max_len, "  "):
                lines.append(ln)
        else:
            lines.append("  No application crashes found in log.")
        lines.append("")
        lines.append("")

        # ---- 5a. BOOT & RECOVERY ----
        boot_recovery = reliability_ctx.get("boot_recovery") or []
        for x in _section_header(
            "5a. BOOT & RECOVERY — Startup repair and cold-boot signals", report_width
        ):
            lines.append(x)
        lines.append("")
        if boot_recovery:
            lines.append(
                "  Events from Startup Repair, Kernel-Boot, or Wininit (recovery / failed boot)."
            )
            lines.append("")
            for evt in boot_recovery[:12]:
                near = (
                    " [near crash]"
                    if _bc("_match_event_to_crash")(
                        evt.get("time", ""), crash_times, _bc("_RELIABILITY_NEAR_CRASH_WINDOW_MIN")
                    )
                    else ""
                )
                body = (
                    f"{evt.get('time', '?')}  {evt.get('subtype', '?')}  "
                    f"ID {evt.get('id', '?')}{near}  {(evt.get('message') or evt.get('note') or '')[:140]}"
                )
                for ln in _wrap_with_prefix("  • ", body.strip(), max_len, "    "):
                    lines.append(ln)
            lines.append("")
            for ln in _wrap_text(
                "FIX: Cold-boot-only failures often trace to BIOS/firmware, storage, chipset, "
                "or GPU init — update those before chasing ntoskrnl.exe itself.",
                max_len, "  ",
            ):
                lines.append(ln)
        else:
            lines.append("  No startup repair or kernel boot failure events in recent logs.")
        lines.append("")
        lines.append("")

        # ---- 5b. RELIABILITY & LIVE KERNEL (on-demand event log) ----
        for x in _section_header("5b. RELIABILITY & LIVE KERNEL — Stability signals", report_width):
            lines.append(x)
        lines.append("")
        stab = reliability_ctx.get("stability_index")
        if stab is not None:
            lines.append(f"  System Stability Index (Reliability Monitor): {stab} (10 = most stable)")
        lk_list = reliability_ctx.get("livekernel") or []
        wer_list = reliability_ctx.get("wer_errors") or []
        if lk_list or wer_list:
            lines.append("  Queried during this analysis only — no background monitoring.")
            lines.append("")
        if lk_list:
            lines.append("  Live Kernel events (driver/hardware faults without full BSOD):")
            for lk in lk_list[:12]:
                near = (
                    " [near crash]"
                    if _bc("_match_event_to_crash")(
                        lk.get("time", ""), crash_times, _bc("_RELIABILITY_NEAR_CRASH_WINDOW_MIN")
                    )
                    else ""
                )
                body = f"{lk.get('time', '?')}  ID {lk.get('id', '?')}{near}  {lk.get('summary', '')}"
                for ln in _wrap_with_prefix("  • ", body.strip(), max_len, "    "):
                    lines.append(ln)
            lines.append("")
        else:
            lines.append("  No Live Kernel events found in recent logs.")
            lines.append("")
        if wer_list:
            lines.append("  Windows Error Reporting (system):")
            for we in wer_list[:10]:
                body = f"{we.get('time', '?')}  ID {we.get('id', '?')}  {(we.get('message') or '')[:120]}"
                for ln in _wrap_with_prefix("  • ", body.strip(), max_len, "    "):
                    lines.append(ln)
            lines.append("")
        if stab is None and not lk_list and not wer_list:
            for ln in _wrap_text(
                "No reliability or live-kernel data returned (run as Administrator, or logs empty).",
                max_len, "  ",
            ):
                lines.append(ln)
        lines.append("")

        # ---- 6. TECHNICAL DETAILS — Dumps and raw WinDbg info ----
        for x in _section_header("6. TECHNICAL DETAILS — Dumps and raw WinDbg info", report_width):
            lines.append(x)
        lines.append("")
        lines.append(f"  Memory dump setting: {dump_config}")
        if windbg_analysis:
            if windbg_analysis.get("dumps_analyzed"):
                lines.append(f"  Minidumps analyzed with WinDbg/CDB: {windbg_analysis['dumps_analyzed']}")
            if windbg_analysis.get("raw"):
                lines.append("  WinDbg (most recent dump):")
                for ln in windbg_analysis["raw"]:
                    lines.append("    " + ln)
        if kernel_dumps:
            lines.append(f"  Kernel minidumps: {MINIDUMP_DIR}")
            for d in kernel_dumps[:5]:
                lines.append("    " + format_minidump_summary_line(d))
        if app_dumps:
            lines.append(f"  Application crash dumps: {len(app_dumps)} file(s) in user folder.")
        counts_str = f"Counts: {len(incidents)} crash incident(s), {len(kernel_dumps)} kernel minidump(s), {len(app_crash_events)} app error(s) in log."
        for ln in _wrap_text(counts_str, max_len, "  "):
            lines.append(ln)
        lines.append("")
    else:
        lines.append("  " + "-" * report_width)
        for ln in _wrap_text(
            "Sections 4-6 (per-crash details, application crashes, and raw WinDbg output) are "
            "hidden in this simple view. Use 'Show technical details' in the GUI to see them.",
            max_len, "  ",
        ):
            lines.append(ln)
        lines.append("")
    # Memory dump registry status (always shown)
    if needs_config:
        prompt = (
            "Windows memory dumps have not been enabled in the Windows registry, having a "
            "memory dump performed when your system crashes will help with discovering the "
            "root cause of your system instability, would you like to enable this feature? (Y/N)"
        )
        for ln in _wrap_text(prompt, max_len, "  "):
            lines.append(ln)
        lines.append("")
    else:
        lines.append(f"  Memory dumps are enabled in the Windows registry ({dump_config}).")
        lines.append("")
    lines.append("  " + "=" * report_width)
    return "\n".join(lines)

def _build_recommendations(events: list, windbg_analysis: dict | None, whea_events: list,
                          thermal_events: list, needs_config: bool, system_ctx: dict | None = None,
                          devices_with_driver_problems: list | None = None,
                          devices_with_generic_driver: list | None = None,
                          reliability_ctx: dict | None = None,
                          fix_plan: dict | None = None) -> list[str]:
    """Ordered fix steps from log-derived plan (legacy path builds plan if missing)."""
    if fix_plan and fix_plan.get("steps"):
        return list(fix_plan["steps"])
    if system_ctx is None:
        system_ctx = {"present_drivers": set(), "has_sata": True, "has_nvme": True, "gpu_vendor": None}
    if devices_with_driver_problems is None:
        devices_with_driver_problems = []
    if devices_with_generic_driver is None:
        devices_with_generic_driver = []
    present = system_ctx.get("present_drivers") or set()
    recs = []
    if windbg_analysis and windbg_analysis.get("recurring_faulting_driver"):
        drv = windbg_analysis["recurring_faulting_driver"]
        cnt = windbg_analysis.get("recurring_count", 2)
        dump_word = "crash dump" if cnt == 1 else "crash dumps"
        recs.append(
            f"Priority (WinDbg): {drv} appeared in {cnt} recent {dump_word} — update or roll back this driver first; it is the most likely cause."
        )
    if devices_with_driver_problems:
        recs.append("Install or update drivers for devices with problems (see Section 3 — Devices with missing or problematic drivers).")
    # Generic driver recommendation deferred to end of action plan (less impactful for CPU/chipset/GPU)
    bugchecks = [e for e in events if e.get("type") == "BugCheck" and e.get("code") not in ("?", "N/A")]
    latest = bugchecks[0] if bugchecks else None
    code_val = None
    p1 = None
    p1_int = None
    whea_component = None
    faulting_driver = windbg_analysis.get("faulting_driver") if windbg_analysis else None
    thermal_near_crash = False
    crash_times_all = [e["time"] for e in events if e.get("time")]
    livekernel_near_crash, wer_near_crash = _bc("_reliability_events_near_crash")(
        reliability_ctx, crash_times_all
    )

    if latest:
        try:
            code_val = int(str(latest.get("code", "")).replace("0x", ""), 16)
        except (ValueError, TypeError):
            pass
        p1 = latest.get("p1") or (windbg_analysis.get("bugcheck_p1") if windbg_analysis else None)
        p1_int = _parse_p1(str(p1)) if p1 is not None else None
        crash_times = [e["time"] for e in events[:5] if e.get("time")]
        for we in whea_events:
            if we.get("component") and _bc("_match_event_to_crash")(
            we["time"], crash_times, _bc("_WHEA_NEAR_CRASH_WINDOW_MIN")
        ):
                whea_component = we["component"]
                break
        for te in thermal_events[:5]:
            if _bc("_match_event_to_crash")(te["time"], crash_times, _bc("_THERMAL_NEAR_CRASH_WINDOW_MIN")):
                thermal_near_crash = True
                break

    drv_base = (faulting_driver or "").lower().replace(".sys", "").replace(".dll", "").strip()

    # Primary: specific to fault; filter lists to only drivers present on this system
    if faulting_driver and drv_base:
        matched = None
        for k in POSSIBLE_DRIVERS:
            if k in drv_base or drv_base == k:
                matched = POSSIBLE_DRIVERS[k]
                break
        if matched:
            cpu_list, pcie_list, fallback_list = matched
            cpu_list = _filter_possible_drivers_list(cpu_list, present, system_ctx)
            pcie_list = _filter_possible_drivers_list(pcie_list, present, system_ctx)
            fallback_list = _filter_possible_drivers_list(fallback_list, present, system_ctx)
            if code_val == 0x124 and p1_int == 0x4 and pcie_list:
                recs.append("PCIe source - update one of: " + "; ".join(pcie_list[:3]))
            elif code_val == 0x124 and p1_int in (0x0, 0x1, None) and cpu_list:
                recs.append("CPU source - update in order (only drivers present on this system):")
                for i, x in enumerate(cpu_list[:4], 1):
                    recs.append(f"  {i}) {x}")
            elif fallback_list:
                recs.append(fallback_list[0])
                if len(fallback_list) > 1:
                    recs.append("Then: " + "; ".join(fallback_list[1:4]))
        else:
            for k in _bc("GENERIC_FAULT_MODULE_DEVICE"):
                if k in drv_base or drv_base == k:
                    _, action = _bc("GENERIC_FAULT_MODULE_DEVICE")[k]
                    if action:
                        recs.append(action)
                    break
            else:
                vendor = _infer_driver_vendor(drv_base)
                recs.append(f"Update or rollback '{faulting_driver}' from device manufacturer" + (f" ({vendor})" if vendor else ""))

    # WHEA-specific
    if code_val == 0x124 and not recs:
        if p1_int == 0x4:
            recs.append("PCIe hardware error: update GPU, NVMe, or other PCIe card drivers; check hardware seating")
        elif p1_int in (0x0, 0x1):
            recs.append("CPU hardware error: update BIOS/UEFI and chipset drivers; disable overclocking; check cooling")
        else:
            recs.append("WHEA hardware error: update BIOS, chipset, GPU, and storage drivers; disable overclocking")

    if whea_component:
        recs.append(f"WHEA identified component: {whea_component} - update firmware/driver for this device")

    if thermal_near_crash:
        recs.append("Thermal event near crash: improve cooling, clean fans, monitor temps, reduce load")

    if livekernel_near_crash:
        recs.insert(
            0,
            "Live Kernel Event near crash: update GPU, chipset, and storage drivers; "
            "check Reliability Monitor (Win+R → perfmon /rel) for matching failures",
        )
    elif (reliability_ctx or {}).get("livekernel"):
        recs.append(
            "Recent Live Kernel Events in the log — review Reliability Monitor (perfmon /rel) "
            "and update drivers if instability continues"
        )

    if wer_near_crash:
        recs.append(
            "Windows Error Reporting logged a system failure near crash time — "
            "see Reliability Monitor history for the failing module"
        )

    # Stop-code specific
    if code_val == 0xEA and "GPU" not in " ".join(recs):
        recs.append("Display driver hung: update or rollback GPU driver")
    elif code_val in (0x0A, 0xD1) and not recs:
        recs.append("Driver IRQL error: update or rollback recent driver changes (often GPU, storage, or network)")

    # Secondary: only if no strong primary, or as final checks
    if not recs:
        recs.append("Update GPU, chipset, storage, and network drivers from manufacturer sites")

    # RAM / memory-test recommendation (memory-related stop codes)
    memory_codes = (0x1A, 0x50, 0x7A, 0xC2, 0xC5, 0x109, 0x14E)
    if code_val in memory_codes or (code_val is None and not recs):
        recs.append("Run Windows Memory Diagnostic (mdsched.exe) to test RAM")

    # Disk / chkdsk recommendation (disk-related stop codes)
    disk_codes = (0x7A, 0x7B, 0xED, 0x50)
    if code_val in disk_codes:
        recs.append("Run chkdsk /f on the system drive (schedule on reboot if needed)")

    # SFC / DISM suggestion (system file repair)
    recs.append("Run sfc /scannow to check system files; if needed, run DISM /Online /Cleanup-Image /RestoreHealth")

    # Generic driver suggestion last (main devices like CPU/chipset/GPU rarely use generic drivers)
    if devices_with_generic_driver:
        recs.append("Consider installing vendor drivers for devices using a generic driver (see Section 3 — Devices using a generic driver).")

    if needs_config:
        recs.append("Enable memory dumps (registry): You will be asked Y/N; type Y to enable (run as Administrator).")

    return recs

def _build_summary(events: list, kernel_dumps: list, full_dump: dict | None, app_dumps: list,
                   windbg_analysis: dict | None, whea_events: list, thermal_events: list,
                   needs_config: bool) -> list[str]:
    """Build a concise summary of key findings."""
    lines = []
    bugchecks = [e for e in events if e.get("type") == "BugCheck" and e.get("code") not in ("?", "N/A")]
    other_crashes = [e for e in events if e.get("type") in ("KernelPower", "UnexpectedShutdown")]

    if not events and not kernel_dumps:
        lines.append("No crash events or kernel dumps found.")
        if app_dumps:
            lines.append(f"Application crashes: {len(app_dumps)} dumps from various programs.")
        return lines

    if bugchecks:
        latest = bugchecks[0]
        code = latest.get("code", "?")
        time_str = latest.get("time", "?")
        code_val = None
        try:
            code_val = int(str(code).replace("0x", ""), 16)
            name, _ = _bc("get_bugcheck_info")(code_val)
        except (ValueError, TypeError):
            name = str(code)
        lines.append(f"Most recent crash: {time_str} - Stop code: {name}")
        if windbg_analysis and windbg_analysis.get("faulting_driver"):
            drv = windbg_analysis["faulting_driver"]
            whea_comp = None
            for we in whea_events:
                if we.get("component") and _bc("_match_event_to_crash")(
                    we["time"], [e["time"] for e in events[:3]], _bc("_WHEA_NEAR_CRASH_WINDOW_MIN")
                ):
                    whea_comp = we["component"]
                    break
            p1 = latest.get("p1") or (windbg_analysis.get("bugcheck_p1") if windbg_analysis else None)
            expl = _bc("get_faulting_device_explanation")(drv, code_val, p1, whea_comp)
            if expl and expl != drv:
                lines.append(f"Faulting module: {drv}")
                for line in expl.replace(" | ", "\n").split("\n"):
                    line = line.strip()
                    if line:
                        lines.append(f"  -> {line}")
            else:
                lines.append(f"Faulting driver: {drv}")
        if code_val == 0x124:
            for we in whea_events:
                if we.get("component") and _bc("_match_event_to_crash")(
                    we["time"], [e["time"] for e in events[:3]], _bc("_WHEA_NEAR_CRASH_WINDOW_MIN")
                ):
                    lines.append(f"Hardware component: {we['component']}")
                    break
        for te in thermal_events[:5]:
            if _bc("_match_event_to_crash")(
                te["time"],
                [e["time"] for e in events[:3] if e.get("time")],
                _bc("_THERMAL_NEAR_CRASH_WINDOW_MIN"),
            ):
                lines.append("Thermal event detected near crash time.")
                break
    elif other_crashes:
        latest = other_crashes[0]
        lines.append(f"Most recent unexpected shutdown: {latest.get('time', '?')}")
        lines.append("No BugCheck recorded - possible power loss or incomplete crash log.")

    lines.append(f"Total crash events found: {len(events)}")
    lines.append(
        f"Kernel minidumps: {len(kernel_dumps)}"
        + (f" (latest: {kernel_dumps[0].get('name', '?')})" if kernel_dumps else "")
    )
    if full_dump:
        lines.append(f"Full memory dump: Present ({full_dump.get('size_mb', '?')} MB)")
    if app_dumps:
        lines.append(f"Application crash dumps: {len(app_dumps)}")
    if needs_config:
        lines.append("Note: Memory dump creation may be disabled - enable for future crash analysis.")
    return lines

_ANALYSIS_TASK_LABELS: dict[str, str] = {
    "events": "Windows crash event log",
    "boot_recovery_pack": "Boot and recovery event log",
    "kernel_dumps": "Minidump folder listing",
    "kernel_pack": "Minidump folder listing and crash dump settings",
    "full_dump": "Full memory dump check",
    "app_dumps": "Application crash dump listing",
    "app_crash_events": "Application crash events",
    "bios_driver_info": "Installed driver inventory",
    "dump_config_tuple": "Crash dump configuration",
    "cdb_path": "Debugging tools (CDB) lookup",
    "whea_events": "WHEA hardware error log",
    "thermal_events": "Thermal event log",
    "pnp_list": "Plug-and-play device list",
    "reliability_ctx": "Reliability Monitor data",
    "windbg_analysis": "Minidump analysis (WinDbg/CDB)",
    "full_driver_inventory": "Full installed driver inventory",
    "storage_context": "Storage and system hardware details",
    "driver_verification": "Crash-linked driver verification",
}

def _analysis_gap_message(task_key: str, exc: Exception | None = None) -> str:
    label = _ANALYSIS_TASK_LABELS.get(task_key, task_key)
    if exc is not None:
        detail = str(exc).strip() or type(exc).__name__
        if len(detail) > 80:
            detail = detail[:77] + "…"
        return f"{label} ({detail})"
    return label

def minidump_without_bugcheck_gap(
    kernel_dumps: list,
    events: list,
    *,
    events_query_failed: bool = False,
) -> str | None:
    """Soft gap when minidumps exist but Event ID 1001 BugCheck rows did not load."""
    if events_query_failed or not kernel_dumps:
        return None
    has_bugcheck = bool(_usable_bugcheck_events(events or []))
    if has_bugcheck:
        return None
    n = len(kernel_dumps)
    dump_word = "minidump" if n == 1 else "minidumps"
    return (
        f"Kernel {dump_word} ({n}) found on disk, but no recent BugCheck "
        "(Event ID 1001) entries appeared in the System event log. Analysis used "
        "minidump data where available; run as Administrator if the crash timeline "
        "looks incomplete."
    )

def _friendly_driver_label(driver: str | None) -> str:
    """Return a short, human-friendly label for a faulting driver (e.g. 'NVIDIA driver (nvlddmkm.sys)')."""
    if not driver:
        return ""
    base = driver.lower().replace(".sys", "").replace(".dll", "").replace(".exe", "").strip()
    for key, (device, _action) in _bc("GENERIC_FAULT_MODULE_DEVICE").items():
        if key in base or base == key:
            return f"{device} ({driver})"
    vendor = _infer_driver_vendor(base)
    if vendor:
        return f"{vendor} ({driver})"
    return driver

def _severity_for_display(events: list, windbg_analysis: dict | None, whea_events: list,
                          code_val: int | None) -> tuple[int, str]:
    """Map findings to a severity level: (0 Low, 1 Moderate, 2 High, 3 Critical)."""
    has_bugcheck = any(e.get("type") == "BugCheck" and e.get("code") not in ("?", "N/A") for e in events)
    recurring = windbg_analysis.get("recurring_faulting_driver") if windbg_analysis else None
    recurring_count = windbg_analysis.get("recurring_count", 0) if windbg_analysis else 0
    faulting = windbg_analysis.get("faulting_driver") if windbg_analysis else None
    if code_val == 0x124 or whea_events:
        return 3, "Critical"
    if recurring and recurring_count >= 2:
        return 2, "High"
    if faulting:
        return 2, "High"
    if has_bugcheck:
        return 1, "Moderate"
    if events:
        return 1, "Moderate"
    return 0, "Low"

def build_report_derivations(fmt_args: tuple) -> dict:
    """Shared analysis derivations for GUI display model and text export."""
    (events, kernel_dumps, full_dump, app_dumps,
     windbg_analysis, whea_events, thermal_events,
     dump_config, dump_val, needs_config,
     logged_in_user, user_crashdumps_display,
     app_crash_events, bios_driver_info,
     system_ctx, devices_with_driver_problems,
     devices_with_generic_driver) = fmt_args[:17]
    reliability_ctx = fmt_args[17] if len(fmt_args) > 17 else None
    if not reliability_ctx:
        reliability_ctx = {"livekernel": [], "wer_errors": [], "stability_index": None}

    code_val, stop_name, stop_desc, has_bugcheck = resolve_crash_code(
        events, windbg_analysis
    )
    confidence = _bc("_analysis_confidence_label")(
        windbg_analysis, has_bugcheck or code_val is not None
    )
    report_ctx = _bc("_crash_report_context")(events, windbg_analysis, whea_events, thermal_events)
    hardware_findings = _bc("build_hardware_findings_from_logs")(
        events,
        whea_events,
        thermal_events,
        windbg_analysis,
        reliability_ctx,
        report_ctx,
        system_ctx,
        code_val,
        stop_name,
    )
    log_coverage = _bc("build_event_log_coverage_summary")(
        events,
        whea_events,
        thermal_events,
        app_crash_events,
        reliability_ctx,
        kernel_dumps,
        windbg_analysis,
        extended_log_attribution=(system_ctx or {}).get("extended_log_attribution"),
    )
    faulting = windbg_analysis.get("faulting_driver") if windbg_analysis else None
    recurring = windbg_analysis.get("recurring_faulting_driver") if windbg_analysis else None
    recurring_count = windbg_analysis.get("recurring_count", 0) if windbg_analysis else 0
    dumps_analyzed = windbg_analysis.get("dumps_analyzed", 0) if windbg_analysis else 0
    driver = faulting

    cause_type = _bc("infer_likely_cause_type")(
        driver, code_val, windbg_analysis, whea_events, events, thermal_events, reliability_ctx,
    )
    fix_focus = derive_report_fix_focus(
        code_val,
        report_ctx,
        driver,
        windbg_analysis,
        cause_type,
        reliability_ctx,
        events,
        whea_events,
        thermal_events,
        system_ctx=system_ctx,
    )
    dump_matches_latest = _dump_matches_recent_events(windbg_analysis, events)
    _lc, _ln, _ld, latest_verified = (
        _verified_stop_for_incident(
            _group_events_by_incident(events)[0], windbg_analysis, events=events
        )
        if events and _group_events_by_incident(events)
        else (None, "", "", False)
    )
    fix_plan = build_crash_fix_plan(
        fix_focus,
        code_val=code_val,
        stop_name=stop_name,
        faulting_driver=driver,
        windbg_analysis=windbg_analysis,
        system_ctx=system_ctx,
        cause_type=cause_type,
        devices_with_generic_driver=devices_with_generic_driver,
        needs_config=needs_config,
        boot_recovery=reliability_ctx.get("boot_recovery") or [],
        dump_matches_latest=dump_matches_latest,
        has_verified_stop=latest_verified,
    )
    fix_plan = dict(fix_plan)
    fix_plan["steps"] = _bc("sanitize_action_plan_steps")(
        fix_plan.get("steps") or [], driver
    )
    driver_verification = (system_ctx or {}).get("driver_verification") or {}
    repair_narrative = driver_verification.get("repair_narrative") or {}
    confidence_summary = _bc("build_crash_confidence_summary")(
        events,
        windbg_analysis,
        driver_verification=driver_verification,
        needs_config=needs_config,
        has_bugcheck=has_bugcheck,
    )
    if system_ctx is not None:
        system_ctx = dict(system_ctx)
        system_ctx["crash_confidence"] = confidence_summary
    plain_english = (
        _bc("_plain_english_from_repair_narrative")(repair_narrative)
        if repair_narrative.get("what_happened")
        else _bc("_build_plain_english_summary")(
            windbg_analysis,
            code_val,
            stop_name,
            stop_desc,
            hardware_findings=hardware_findings,
            log_coverage=log_coverage,
            system_ctx=system_ctx,
            fix_plan=fix_plan,
        )
    )
    recommendations = _build_recommendations(
        events, windbg_analysis, whea_events, thermal_events, needs_config,
        system_ctx, devices_with_driver_problems, devices_with_generic_driver,
        reliability_ctx,
        fix_plan=fix_plan,
    )
    recommendations = _bc("merge_verification_action_steps")(
        driver_verification, recommendations, faulting_driver=driver
    )
    _prereq_steps = ((system_ctx or {}).get("minidump_prerequisites") or {}).get("action_steps") or []
    for step in _prereq_steps:
        if step not in recommendations:
            recommendations.append(step)
    for step in (system_ctx or {}).get("wer_dump_recovery", {}).get("action_steps") or []:
        if step not in recommendations:
            recommendations.append(step)
    sev_level, sev_name = _bc("_severity_for_display")(events, windbg_analysis, whea_events, code_val)

    if repair_narrative.get("headline"):
        cause_title = repair_narrative["headline"]
    elif (
        driver
        and dump_matches_latest
        and (repair_narrative.get("what_failed") or {}).get("status") == "verified"
    ):
        cause_title = _bc("_friendly_driver_label")(driver)
    elif driver and dump_matches_latest:
        cause_title = _bc("_friendly_driver_label")(driver)
    elif code_val == 0x124 or whea_events:
        cause_title = "A hardware error (WHEA)"
    elif has_bugcheck:
        cause_title = stop_name or "Kernel crash"
    elif events:
        cause_title = "Unexpected shutdowns (no stop code recorded)"
    else:
        cause_title = "No crashes found"

    attributed_pct = 0
    if recurring and recurring_count >= 2 and dumps_analyzed:
        attributed_pct = round(100 * recurring_count / dumps_analyzed)

    minidump_prereqs = (system_ctx or {}).get("minidump_prerequisites") or assess_minidump_prerequisites()
    capture_readiness = build_capture_readiness(
        needs_config=needs_config,
        dump_config=dump_config,
        kernel_dumps=kernel_dumps,
        events=events,
        windbg_analysis=windbg_analysis,
        cdb_repair=(system_ctx or {}).get("cdb_repair"),
        minidump_prereqs=minidump_prereqs,
    )
    incident_timeline = build_incident_timeline(
        events,
        reliability_ctx=reliability_ctx,
        windbg_analysis=windbg_analysis,
        kernel_dumps=kernel_dumps,
        extended_log_attribution=(system_ctx or {}).get("extended_log_attribution"),
    )

    return {
        "events": events,
        "kernel_dumps": kernel_dumps,
        "full_dump": full_dump,
        "app_dumps": app_dumps,
        "windbg_analysis": windbg_analysis,
        "whea_events": whea_events,
        "thermal_events": thermal_events,
        "dump_config": dump_config,
        "dump_val": dump_val,
        "needs_config": needs_config,
        "logged_in_user": logged_in_user,
        "user_crashdumps_display": user_crashdumps_display,
        "app_crash_events": app_crash_events,
        "bios_driver_info": bios_driver_info,
        "system_ctx": system_ctx,
        "devices_with_driver_problems": devices_with_driver_problems,
        "devices_with_generic_driver": devices_with_generic_driver,
        "reliability_ctx": reliability_ctx,
        "code_val": code_val,
        "stop_name": stop_name,
        "stop_desc": stop_desc,
        "has_bugcheck": has_bugcheck,
        "confidence": confidence,
        "report_ctx": report_ctx,
        "hardware_findings": hardware_findings,
        "log_coverage": log_coverage,
        "driver": driver,
        "faulting": faulting,
        "recurring": recurring,
        "recurring_count": recurring_count,
        "dumps_analyzed": dumps_analyzed,
        "cause_type": cause_type,
        "fix_focus": fix_focus,
        "fix_plan": fix_plan,
        "plain_english": plain_english,
        "recommendations": recommendations,
        "driver_verification": driver_verification,
        "crash_confidence": confidence_summary,
        "boot_failure_playbook": build_boot_failure_playbook_steps(
            reliability_ctx.get("boot_recovery") or [],
            system_ctx=system_ctx,
            dump_matches_latest=dump_matches_latest,
            has_verified_stop=latest_verified,
        ),
        "severity_level": sev_level,
        "severity_name": sev_name,
        "cause_title": cause_title,
        "attributed_pct": attributed_pct,
        "capture_readiness": capture_readiness,
        "incident_timeline": incident_timeline,
        "log_read_windows": lrw.read_windows_as_dict(),
    }

def format_output_from_fmt_args(fmt_args: tuple, **kwargs) -> str:
    """Build text report from the 18-slot gather_report_data tuple."""
    if len(fmt_args) < 17:
        raise ValueError("fmt_args must have at least 17 elements")
    rel = fmt_args[17] if len(fmt_args) > 17 else None
    return format_output(
        fmt_args[0], fmt_args[1], fmt_args[2], fmt_args[3],
        fmt_args[4], fmt_args[5], fmt_args[6],
        fmt_args[7], fmt_args[8], fmt_args[9],
        fmt_args[10], fmt_args[11], fmt_args[12], fmt_args[13],
        fmt_args[14], fmt_args[15], fmt_args[16],
        reliability_ctx=rel,
        **kwargs,
    )

def build_display_model(fmt_args: tuple) -> dict:
    """Turn the format_output() argument tuple into structured fields for a rich GUI (Option B).

    Reuses the same analysis helpers as the text report so the GUI and report stay consistent.
    """
    deriv = build_report_derivations(fmt_args)
    events = deriv["events"]
    windbg_analysis = deriv["windbg_analysis"]
    whea_events = deriv["whea_events"]
    thermal_events = deriv["thermal_events"]
    bios_driver_info = deriv["bios_driver_info"]
    system_ctx = deriv["system_ctx"]
    devices_with_driver_problems = deriv["devices_with_driver_problems"]
    devices_with_generic_driver = deriv["devices_with_generic_driver"]
    reliability_ctx = deriv["reliability_ctx"]
    code_val = deriv["code_val"]
    stop_name = deriv["stop_name"]
    driver = deriv["driver"]
    cause_type = deriv["cause_type"]
    fix_focus = deriv["fix_focus"]
    fix_plan = deriv["fix_plan"]
    recurring_count = deriv["recurring_count"]
    dumps_analyzed = deriv["dumps_analyzed"]
    recurring = deriv["recurring"]

    # Per-incident summaries (Section 4 equivalent, as structured rows)
    crash_times = [e["time"] for e in events if e.get("time")]
    incidents_model = []
    incidents = _group_events_by_incident(events, window_minutes=2) if events else []
    for idx, group in enumerate(incidents[:8]):
        evt = next((e for e in group if e.get("type") == "BugCheck"), group[0])
        evt = next((e for e in group if e.get("type") == "KernelPower" and evt.get("type") != "BugCheck"), evt)
        inc_name = ""
        inc_code_val = None
        if evt.get("code") and str(evt["code"]) not in ("?", "N/A", "0x00000000"):
            try:
                inc_code_val = int(str(evt["code"]).replace("0x", ""), 16)
                inc_name, _ = _bc("get_bugcheck_info")(inc_code_val)
            except (ValueError, TypeError):
                inc_name = str(evt["code"])
        definitive = _bc("_build_definitive_cause")(
            evt, windbg_analysis, whea_events, thermal_events, crash_times,
            is_most_recent=(idx == 0), reliability_ctx=reliability_ctx,
        )
        cause_line = ""
        if definitive:
            parts = [d.strip() for d in definitive if d.strip()]
            if parts:
                cause_line = parts[0]
        incidents_model.append({
            "time": evt.get("time", "?"),
            "types": ", ".join(sorted(set(e.get("type", "") for e in group))),
            "stop_code": inc_name or (evt.get("note", "") or ""),
            "cause": cause_line,
        })

    common_devices = (bios_driver_info or {}).get("drivers") or []
    inventory = device_inventory_for_matching(bios_driver_info)
    culprit_ctx = resolve_crash_culprit_context(
        driver,
        bios_driver_info,
        code_val=code_val,
        system_ctx=system_ctx,
        cause_type=cause_type,
        fix_plan=fix_plan,
        has_crash_context=True,
    )
    culprit_callout = culprit_ctx["culprit_callout"]
    culprit_driver_info = culprit_ctx["culprit_driver_info"]
    pnp_list = (system_ctx or {}).get("pnp_list") or []
    driver_update_options = []
    if cause_type.get("driver_actionable") and driver:
        driver_update_options = _bc("build_driver_update_options")(
            driver, pnp_list, system_ctx, bios_driver_info, inventory
        )
    if _bc("_needs_platform_driver_links")(fix_focus=fix_focus):
        platform_opts = build_platform_update_options(
            system_ctx,
            code_val=code_val,
            report_ctx=deriv["report_ctx"],
            faulting_driver=driver,
            bios_driver_info=bios_driver_info,
            reliability_ctx=reliability_ctx,
            crash_times=[e["time"] for e in events if e.get("time")],
            fix_focus=fix_focus,
        )
        driver_update_options = _merge_update_options(driver_update_options, platform_opts)

    action_plan_link_basis = _bc("_describe_action_plan_link_basis")(
        code_val, deriv["report_ctx"], driver, cause_type, system_ctx, reliability_ctx,
        fix_plan=fix_plan,
    )

    crash_timeline = compute_crash_timeline(events)
    incident_timeline = build_incident_timeline(
        events,
        reliability_ctx=reliability_ctx,
        windbg_analysis=windbg_analysis,
        kernel_dumps=deriv["kernel_dumps"],
        extended_log_attribution=(deriv.get("system_ctx") or {}).get("extended_log_attribution"),
    )

    drv_ver = deriv.get("driver_verification") or {}
    narrative = drv_ver.get("repair_narrative") or {}
    driver = deriv["driver"]
    if narrative and not narrative.get("dump_matches_latest"):
        if (narrative.get("what_failed") or {}).get("status") != "verified":
            driver = None

    return {
        "cause_title": deriv["cause_title"],
        "cause_subtitle": narrative.get("subtitle") or "",
        "crash_repair_narrative": narrative,
        "driver": driver,
        "cause_type": cause_type,
        "culprit_driver_info": culprit_driver_info,
        "culprit_device_names": sorted(culprit_ctx["culprit_device_names"]),
        "driver_update_options": driver_update_options,
        "action_plan_link_basis": action_plan_link_basis,
        "report_ctx": deriv["report_ctx"],
        "hardware_findings": deriv["hardware_findings"],
        "log_coverage": deriv["log_coverage"],
        "confidence": deriv["confidence"],
        "severity_level": deriv["severity_level"],
        "severity_name": deriv["severity_name"],
        "plain_english": deriv["plain_english"],
        "fix_plan": fix_plan,
        "recommendations": deriv["recommendations"],
        "driver_verification": deriv.get("driver_verification") or {},
        "crash_confidence": deriv.get("crash_confidence") or {},
        "boot_failure_playbook": deriv.get("boot_failure_playbook") or [],
        "analysis_elapsed_ms": deriv.get("analysis_elapsed_ms"),
        "dumps_analyzed": dumps_analyzed,
        "recurring_count": recurring_count,
        "attributed_pct": deriv["attributed_pct"],
        "last_crash": events[0]["time"] if events else "",
        "stop_name": stop_name,
        "stop_name_friendly": (
            "Hardware error (WHEA)" if code_val == 0x124
            else (stop_name.replace("_", " ").title() if stop_name else "")
        ),
        "stop_code_val": code_val,
        "incidents": incidents_model,
        "app_crashes": deriv["app_crash_events"],
        "bios_driver_info": bios_driver_info,
        "culprit_callout": culprit_callout,
        "data_gaps": list(system_ctx.get("data_gaps") or []),
        "devices_with_driver_problems": devices_with_driver_problems,
        "devices_with_generic_driver": devices_with_generic_driver,
        "ssd_firmware": list((system_ctx or {}).get("ssd_firmware") or []),
        "secondary_firmware": list((system_ctx or {}).get("secondary_firmware") or []),
        "system_ctx": system_ctx,
        "raw_windbg": (windbg_analysis.get("raw") if windbg_analysis else []) or [],
        "kernel_dumps": deriv["kernel_dumps"],
        "app_dumps": deriv["app_dumps"],
        "dump_config": deriv["dump_config"],
        "needs_config": deriv["needs_config"],
        "logged_in_user": deriv["logged_in_user"],
        "crash_count": len(events),
        "crash_timeline": crash_timeline,
        "incident_timeline": incident_timeline,
        "reliability_ctx": reliability_ctx,
        "windbg_dump_file": (
            (windbg_analysis or {}).get("analysis_source_dump")
            or (windbg_analysis or {}).get("dump_file")
        ),
        "newest_dump_mismatch": bool(
            (windbg_analysis or {}).get("newest_dump_mismatch")
        ),
        "capture_readiness": deriv.get("capture_readiness") or {},
    }
