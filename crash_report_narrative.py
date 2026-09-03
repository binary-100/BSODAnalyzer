"""Cause typing and log narrative helpers (extracted from bsod_crash_report)."""

from __future__ import annotations

from datetime import datetime

import log_read_windows as lrw

from crash_report_culprit import DRIVER_TO_HARDWARE, _infer_driver_vendor
from crash_report_fix_plan import _GPU_DRIVER_FRAGMENTS
from crash_report_events import parse_p1 as _parse_p1
from crash_report_timeline import _dump_matches_event_time, _dump_matches_recent_events


def _ba(name: str):
    """Lazy bsod_analyzer lookup — admin checks and stable re-export surface."""
    import bsod_analyzer as ba

    return getattr(ba, name)


def _bc(name: str):
    """Lazy bsod_crash_report lookup — avoids import cycles during module load."""
    import bsod_crash_report as bc

    return getattr(bc, name)


def infer_likely_cause_type(
    driver: str | None,
    code_val: int | None,
    windbg_analysis: dict | None,
    whea_events: list,
    events: list,
    thermal_events: list | None = None,
    reliability_ctx: dict | None = None,
) -> dict:
    """Classify crash cause for Summary: hardware vs driver vs platform vs mixed."""
    drv_base = (driver or "").lower().replace(".sys", "").replace(".dll", "").replace(".exe", "").strip()
    crash_times = [e["time"] for e in events if e.get("time")]
    whea_component = None
    for we in whea_events or []:
        if we.get("component") and _match_event_to_crash(
            we["time"], crash_times, _bc("_WHEA_NEAR_CRASH_WINDOW_MIN")
        ):
            whea_component = we["component"]
            break
    thermal_near = False
    for te in (thermal_events or [])[:5]:
        if _match_event_to_crash(
            te.get("time", ""), crash_times, _bc("_THERMAL_NEAR_CRASH_WINDOW_MIN")
        ):
            thermal_near = True
            break
    livekernel_near, _ = _reliability_events_near_crash(reliability_ctx, crash_times)

    if drv_base in _bc("_PLATFORM_CPU_MODULES"):
        return {
            "label": "Platform (BIOS / chipset / CPU)",
            "detail": "The faulting module is a CPU/platform identifier — update BIOS, chipset software, and cooling rather than a single device driver.",
            "driver_actionable": False,
        }

    if drv_base in _bc("_KERNEL_SHIM_MODULES") or (
        drv_base and drv_base in _bc("GENERIC_FAULT_MODULE_DEVICE")
        and drv_base not in DRIVER_TO_HARDWARE
        and not _infer_driver_vendor(drv_base)
    ):
        return {
            "label": "Mixed — kernel or framework module",
            "detail": "Windows reported a core component at the crash site; the real cause is usually a driver or hardware underneath (see Action Plan).",
            "driver_actionable": False,
        }

    if code_val == 0x124:
        if drv_base and drv_base not in _bc("_PLATFORM_CPU_MODULES") and drv_base not in _bc("_KERNEL_SHIM_MODULES"):
            return {
                "label": "Mixed — WHEA with named module",
                "detail": f"Uncorrectable hardware error (0x124) with module '{driver}' — may be failing hardware or that device's driver/firmware.",
                "driver_actionable": True,
            }
        if whea_component:
            return {
                "label": "Hardware (WHEA)",
                "detail": f"Windows logged a fatal hardware error. Component: {whea_component}.",
                "driver_actionable": False,
            }
        return {
            "label": "Hardware (WHEA)",
            "detail": "Uncorrectable hardware error — often CPU, RAM, GPU, storage, or power delivery; check WHEA details in Crash Details.",
            "driver_actionable": False,
        }

    if thermal_near and not drv_base:
        return {
            "label": "Hardware (thermal)",
            "detail": "Thermal throttling or shutdown was logged near the crash time — improve cooling and airflow.",
            "driver_actionable": False,
        }

    if livekernel_near and not drv_base:
        return {
            "label": "Driver instability (live kernel)",
            "detail": "Windows logged a Live Kernel Event near the crash — often a driver fault that did not produce a full BSOD. Update GPU, chipset, and storage drivers.",
            "driver_actionable": True,
        }

    if code_val in _bc("_HARDWARE_LEAN_STOP_CODES") and not drv_base:
        return {
            "label": "Hardware (CPU / platform)",
            "detail": "Stop code points at a hardware-level fault (machine check or unexpected trap) with no specific driver named in the dump.",
            "driver_actionable": False,
        }

    if drv_base and (drv_base in DRIVER_TO_HARDWARE or _infer_driver_vendor(drv_base)):
        recurring = windbg_analysis and windbg_analysis.get("recurring_count", 0) >= 2
        detail = f"Minidump analysis points at '{driver}'"
        if recurring:
            detail += " across multiple recent crashes."
        else:
            detail += "."
        return {
            "label": "Driver / software",
            "detail": detail,
            "driver_actionable": True,
        }

    if code_val in (0x0A, 0xD1, 0xEA, 0x133, 0xFE, 0x10E) and drv_base:
        return {
            "label": "Driver / software",
            "detail": f"Driver-related stop code with faulting module '{driver}'.",
            "driver_actionable": True,
        }

    if code_val is not None:
        return {
            "label": "Uncertain",
            "detail": "A stop code was recorded but no specific updatable driver was identified — use Action Plan for broader checks (drivers, memory, storage).",
            "driver_actionable": False,
        }

    return {
        "label": "Uncertain",
        "detail": "Not enough crash detail to classify — run as Administrator and ensure minidumps are enabled.",
        "driver_actionable": False,
    }

def build_event_log_coverage_summary(
    events: list,
    whea_events: list,
    thermal_events: list,
    app_crash_events: list,
    reliability_ctx: dict | None,
    kernel_dumps: list,
    windbg_analysis: dict | None,
    extended_log_attribution: dict | None = None,
) -> dict:
    """Describe which Windows logs were read (not every log on the PC — targeted sources)."""
    rel = reliability_ctx or {}
    lk = rel.get("livekernel") or []
    wer = rel.get("wer_errors") or []
    boot_recovery = rel.get("boot_recovery") or []
    dumps_n = len(kernel_dumps or [])
    analyzed = (windbg_analysis or {}).get("dumps_analyzed") or 0
    ext = extended_log_attribution or {}
    src = ext.get("sources_scanned") or {}
    wer_n = int(src.get("wer_reports_found") or 0)
    setup_n = int(src.get("setupapi_entries") or 0)
    cbs_n = int(src.get("cbs_entries") or 0)
    lines = [
        f"System log — BugCheck / unexpected shutdown / kernel power: {len(events)} recent event(s)",
        f"Boot & recovery (Startup Repair / Kernel-Boot): {len(boot_recovery)} event(s)",
        f"WHEA-Logger (hardware errors): {len(whea_events)} event(s)",
        f"Application log — program crashes: {len(app_crash_events)} event(s)",
        f"Kernel-Power thermal log: {len(thermal_events)} event(s)",
        f"Reliability / Live Kernel: {len(lk)} live-kernel, {len(wer)} WER system error(s)",
        f"Minidumps on disk: {dumps_n}; analyzed with WinDbg: {analyzed}",
        f"Extended attribution: WER archive/queue {wer_n} report(s), "
        f"setupapi.dev.log {setup_n} near-incident change(s), CBS {cbs_n} servicing hint(s)",
    ]
    window_lines = lrw.read_windows_detail_lines()
    return {
        "summary_line": (
            f"Reviewed {len(events)} system crash events, {len(whea_events)} WHEA hardware errors, "
            f"{len(app_crash_events)} app crashes, {len(thermal_events)} thermal entries, "
            f"{len(lk)} live-kernel + {len(wer)} WER entries; "
            f"{analyzed} of {dumps_n} minidump(s) analyzed."
        ),
        "detail_lines": lines,
        "read_window_lines": window_lines,
        "read_windows": lrw.read_windows_as_dict(),
    }

def build_hardware_findings_from_logs(
    events: list,
    whea_events: list,
    thermal_events: list,
    windbg_analysis: dict | None,
    reliability_ctx: dict | None,
    report_ctx: dict,
    system_ctx: dict | None,
    code_val: int | None,
    stop_name: str,
) -> list[str]:
    """Concrete hardware clues from event logs + minidump (shown on Summary)."""
    findings: list[str] = []
    crash_times = [e["time"] for e in events if e.get("time")]
    ctx = system_ctx or {}
    p1_label = report_ctx.get("p1_source_label") or ""
    whea_near = [
        we for we in (whea_events or [])
        if _match_event_to_crash(we.get("time", ""), crash_times, _bc("_WHEA_NEAR_CRASH_WINDOW_MIN"))
    ]

    bugchecks = [
        e for e in events
        if e.get("type") == "BugCheck" and e.get("code") not in ("?", "N/A")
    ]
    if bugchecks:
        evt = bugchecks[0]
        code_s = evt.get("code", "?")
        friendly = stop_name.replace("_", " ") if stop_name else code_s
        findings.append(
            f"System log (BugCheck {evt.get('type', '')}): {friendly} at {evt.get('time', '?')} "
            f"({code_s})"
        )
        if evt.get("p1") and str(evt["p1"]) not in ("?", ""):
            findings.append(f"  BugCheck parameter 1: {evt['p1']}")

    for we in whea_near[:3]:
        comp = (we.get("component") or "").strip()
        if comp:
            findings.append(f"WHEA-Logger: hardware component reported — {comp} ({we.get('time', '?')})")
        elif we.get("message"):
            findings.append(
                f"WHEA-Logger: fatal hardware error at {we.get('time', '?')} "
                f"({(we.get('message') or '')[:100]}…)"
            )

    if code_val == 0x124 and p1_label:
        findings.append(f"WHEA stop code detail: {p1_label}")

    drv = (windbg_analysis or {}).get("faulting_driver") if windbg_analysis else None
    recurring = (windbg_analysis or {}).get("recurring_faulting_driver") if windbg_analysis else None
    if recurring:
        findings.append(
            f"Minidump (WinDbg): same faulting module in multiple dumps — {recurring}"
        )
    elif drv:
        drv_base = drv.lower().replace(".sys", "").replace(".dll", "").strip()
        if drv_base in _bc("_PLATFORM_CPU_MODULES"):
            findings.append(
                f"Minidump (WinDbg): faulting module {drv} — "
                f"{_bc("_detected_cpu_platform_label")(ctx)} identifier (chipset/BIOS driver path, not a GPU app)"
            )
        elif drv_base in _bc("_MISLEADING_FAULT_MODULES"):
            device, _ = _bc("GENERIC_FAULT_MODULE_DEVICE").get(drv_base, ("Windows component", ""))
            findings.append(
                f"Minidump (WinDbg): stop location {drv} ({device}) — often not the driver to update"
            )
        elif drv_base in _GPU_DRIVER_FRAGMENTS:
            findings.append(f"Minidump (WinDbg): graphics-related module {drv}")
        else:
            vendor = _infer_driver_vendor(drv_base)
            findings.append(
                f"Minidump (WinDbg): faulting driver module {drv}"
                + (f" ({vendor})" if vendor else "")
            )
        stacks = (windbg_analysis or {}).get("stack_frames") or []
        if stacks and drv_base in _bc("_MISLEADING_FAULT_MODULES"):
            findings.append(f"  Call stack (top): {' → '.join(stacks[:3])}")

    for te in (thermal_events or [])[:5]:
        if _match_event_to_crash(te.get("time", ""), crash_times, _bc("_THERMAL_NEAR_CRASH_WINDOW_MIN")):
            findings.append(f"Thermal log: event near crash at {te.get('time', '?')}")

    rel = reliability_ctx or {}
    for lk in (rel.get("livekernel") or [])[:5]:
        if _match_event_to_crash(lk.get("time", ""), crash_times, _bc("_RELIABILITY_NEAR_CRASH_WINDOW_MIN")):
            findings.append(
                f"Live Kernel event near crash: {_summarize_livekernel_message(lk.get('summary') or lk.get('message') or '', lk.get('id'))} "
                f"({lk.get('time', '?')})"
            )
    for we in (rel.get("wer_errors") or [])[:3]:
        if _match_event_to_crash(we.get("time", ""), crash_times, _bc("_RELIABILITY_NEAR_CRASH_WINDOW_MIN")):
            msg = (we.get("message") or "")[:80]
            findings.append(f"Windows Error Reporting near crash: {msg or 'system failure'} ({we.get('time', '?')})")

    return findings[:14]

def _user_friendly_stop_summary(
    stop_name: str,
    code_val: int | None,
    stop_desc: str,
    *,
    p1_source_label: str = "",
) -> str:
    """Short stop-code explanation without internal Windows names."""
    if code_val == 0x124:
        if p1_source_label:
            return (
                "Windows logged an uncorrectable hardware error (WHEA). "
                f"The System log points at: {p1_source_label}."
            )
        return (
            "Windows detected a serious hardware error (WHEA). "
            "See Action Plan for steps matched to your log details."
        )
    if stop_name:
        readable = stop_name.replace("_", " ").replace("UNCORRECTABLE", "uncorrectable").strip()
        if readable.upper().startswith("WHEA"):
            return (
                "Windows reported a hardware error. Try chipset drivers, BIOS, and your PC maker's "
                "support downloads (see Action Plan)."
            )
        return f"Windows reported: {readable}. {stop_desc}"
    return stop_desc

def _plain_english_from_repair_narrative(narrative: dict | None) -> str:
    """Plain-language Summary text from structured repair narrative."""
    n = narrative or {}
    parts: list[str] = []
    if n.get("what_happened"):
        parts.append(n["what_happened"])
    wf = n.get("what_failed") or {}
    if wf.get("summary"):
        parts.append(wf["summary"])
    targets = n.get("repair_targets") or []
    if targets:
        parts.append("What to check on this PC:")
        for t in targets[:10]:
            ver = f" (installed {t['version']})" if t.get("version") else ""
            role = t.get("role") or ""
            line = f"• {t.get('label') or '?'}{ver}"
            if role:
                line += f" — {role}"
            parts.append(line)
    why = n.get("why_this_order") or n.get("how_sure")
    if why:
        parts.append(f"Why this order: {why}")
    if n.get("older_incident_note"):
        parts.append(n["older_incident_note"])
    parts.append("Follow the numbered steps on the Action Plan tab.")
    return "\n\n".join(parts)

def _build_plain_english_summary(
    windbg_analysis: dict | None,
    code_val: int | None,
    stop_name: str,
    stop_desc: str,
    *,
    hardware_findings: list[str] | None = None,
    log_coverage: dict | None = None,
    system_ctx: dict | None = None,
    fix_plan: dict | None = None,
) -> str:
    """Plain-language summary for the Summary tab with log-derived hardware detail."""
    if not windbg_analysis and code_val is None:
        return "No blue-screen crash with a stop code was found in the event logs."

    fp_pre = fix_plan or {}
    p1_label = fp_pre.get("p1_source_label") or ""

    if not windbg_analysis:
        paragraphs = [
            _user_friendly_stop_summary(
                stop_name, code_val, stop_desc, p1_source_label=p1_label,
            )
        ]
        paragraphs.append(
            "No minidump was available, so the tool could not name a specific driver file."
        )
    else:
        drv = windbg_analysis.get("faulting_driver")
        recurring = windbg_analysis.get("recurring_faulting_driver")
        drv_base = (drv or "").lower().replace(".sys", "").replace(".dll", "").strip()
        paragraphs: list[str] = []

        if code_val == 0x124:
            platform = _bc("_detected_cpu_platform_label")(system_ctx)
            paragraphs.append(
                _user_friendly_stop_summary(
                    stop_name, code_val, stop_desc, p1_source_label=p1_label,
                )
                + (f" This system is detected as {platform}." if platform else "")
            )

        if recurring:
            cnt = windbg_analysis.get("recurring_count", 2)
            dump_word = "recent crash" if cnt == 1 else "recent crashes"
            paragraphs.append(
                f"The same driver file ({recurring}) showed up in {cnt} {dump_word}. "
                "That is a strong sign you should update or roll back that driver from the maker's website."
            )
        elif drv:
            if drv_base in _bc("_PLATFORM_CPU_MODULES"):
                paragraphs.append(
                    f"The crash report points at the processor platform ({drv}) — "
                    f"{_bc("_detected_cpu_platform_label")(system_ctx)}. "
                    "Update chipset drivers and BIOS from the CPU vendor and your PC maker."
                )
            elif drv_base in _bc("_MISLEADING_FAULT_MODULES") or drv_base in _bc("_KERNEL_SHIM_MODULES"):
                device, _action = _bc("GENERIC_FAULT_MODULE_DEVICE").get(
                    drv_base, ("a Windows component", "")
                )
                paragraphs.append(
                    f"The report names {drv} ({device}). That is often where Windows stopped, not the "
                    "driver that actually needs updating. For this crash type, start with chipset drivers "
                    "and BIOS on the Action Plan tab."
                )
            else:
                vendor = _infer_driver_vendor(drv_base)
                vendor_hint = f" ({vendor})" if vendor else ""
                paragraphs.append(
                    f"Analysis suggests a problem with the driver file {drv}{vendor_hint}. "
                    "Download an updated driver from the device or PC manufacturer's website."
                )
        elif code_val is not None and code_val != 0x124:
            paragraphs.append(_user_friendly_stop_summary(stop_name, code_val, stop_desc))

        if not paragraphs:
            paragraphs.append(stop_desc or "A system crash was recorded.")

        fp = fix_plan or {}
        if fp.get("headline"):
            paragraphs.append(
                f"What to do first: open the Action Plan tab — {fp['headline']}. "
                "Follow the numbered steps there (they match what your logs reported)."
            )
        elif code_val == 0x124 or drv_base in _bc("_PLATFORM_CPU_MODULES") | _bc("_MISLEADING_FAULT_MODULES"):
            paragraphs.append(
                "What to do first: open the Action Plan tab and follow the numbered fix steps."
            )
        elif recurring or (
            drv and drv_base not in _bc("_MISLEADING_FAULT_MODULES") and drv_base not in _bc("_KERNEL_SHIM_MODULES")
        ):
            paragraphs.append(
                "What to do first: use the Action Plan steps and download links for "
                f"{recurring or drv}, then restart."
            )

    hf = [f for f in (hardware_findings or []) if f.strip()]
    if hf:
        paragraphs.append(
            "What the logs show:\n" + "\n".join(f"• {line}" for line in hf)
        )

    cov = log_coverage or {}
    if cov.get("summary_line"):
        paragraphs.append(
            "Logs reviewed (targeted Windows sources, not every log on the PC):\n"
            + cov["summary_line"]
        )
        for line in cov.get("detail_lines") or []:
            paragraphs.append(f"• {line}")

    conf = (system_ctx or {}).get("crash_confidence") if system_ctx else None
    if conf and conf.get("lines"):
        paragraphs.insert(0, "\n".join(conf["lines"]))

    return "\n\n".join(paragraphs)

def _summarize_livekernel_message(message: str, event_id: int | None) -> str:
    """Short plain-English hint from a Live Kernel event message."""
    m = (message or "").lower()
    if "display" in m or "dxg" in m or "gpu" in m or "graphics" in m:
        return "Graphics / display driver instability"
    if "storage" in m or "disk" in m or "nvme" in m or "stor" in m:
        return "Storage driver or disk instability"
    if "network" in m or "ndis" in m or "wifi" in m:
        return "Network driver instability"
    if "usb" in m:
        return "USB driver or device instability"
    if event_id == 141:
        return "Unresponsive driver (Event 141)"
    if event_id == 193:
        return "Bugcheck-related live kernel report"
    if message:
        return message[:120]
    return "Live kernel event (driver or hardware fault without full BSOD)"

def _reliability_events_near_crash(
    reliability_ctx: dict | None,
    crash_times: list[str],
    window_minutes: int | None = None,
) -> tuple[bool, bool]:
    """Return (livekernel_near_crash, wer_near_crash)."""
    if window_minutes is None:
        window_minutes = _bc("_RELIABILITY_NEAR_CRASH_WINDOW_MIN")
    ctx = reliability_ctx or {}
    lk_near = any(
        _match_event_to_crash(e.get("time", ""), crash_times, window_minutes)
        for e in (ctx.get("livekernel") or [])[:12]
    )
    wer_near = any(
        _match_event_to_crash(e.get("time", ""), crash_times, window_minutes)
        for e in (ctx.get("wer_errors") or [])[:12]
    )
    return lk_near, wer_near

def _match_event_to_crash(
    evt_time: str,
    crash_times: list[str],
    window_minutes: int | None = None,
) -> bool:
    """Check if event is within window of any crash."""
    if window_minutes is None:
        window_minutes = _bc("_WHEA_NEAR_CRASH_WINDOW_MIN")
    try:
        et = datetime.strptime(evt_time, "%Y-%m-%d %H:%M:%S")
        for ct in crash_times:
            try:
                ct_dt = datetime.strptime(ct, "%Y-%m-%d %H:%M:%S")
                if abs((et - ct_dt).total_seconds()) <= window_minutes * 60:
                    return True
            except ValueError:
                pass
    except ValueError:
        pass
    return False

def boot_events_near_crash(
    boot_recovery: list | None,
    crash_times: list[str],
    *,
    window_minutes: int = 15,
) -> list[dict]:
    """Boot/recovery rows within window_minutes of any crash time (searches full list)."""
    if not boot_recovery or not crash_times:
        return []
    return [
        e for e in boot_recovery
        if e.get("time") and _match_event_to_crash(e["time"], crash_times, window_minutes)
    ]

def _build_definitive_cause(evt: dict, windbg_analysis: dict | None, whea_events: list,
                            thermal_events: list, crash_times: list, is_most_recent: bool = False,
                            reliability_ctx: dict | None = None) -> list[str]:
    """Build definitive cause lines for a crash event."""
    causes = []
    code = evt.get("code")
    evt_time = evt.get("time", "")
    code_val = None
    if code and str(code) not in ("?", "N/A"):
        try:
            code_val = int(str(code).replace("0x", ""), 16)
        except (ValueError, TypeError):
            pass
    if code_val is None and is_most_recent and windbg_analysis:
        if _dump_matches_event_time(windbg_analysis, evt_time):
            raw = windbg_analysis.get("bugcheck_code")
            if raw is not None:
                try:
                    code_val = int(str(raw).replace("0x", ""), 16)
                except (ValueError, TypeError):
                    pass

    dump_matches = _dump_matches_event_time(windbg_analysis, evt_time)

    # Faulting driver/module from minidump (only when dump time matches this incident)
    driver_stop_codes = (0x0A, 0x0D, 0x1E, 0x3B, 0x50, 0x7E, 0x8E, 0xD1, 0xEA, 0x133, 0x139)
    whea_component = None
    if code_val == 0x124:
        for we in whea_events:
            if _match_event_to_crash(
                we["time"], [evt_time], _bc("_INCIDENT_WHEA_WINDOW_MIN")
            ) and we.get("component"):
                whea_component = we["component"]
                break

    if is_most_recent and dump_matches and windbg_analysis and windbg_analysis.get("faulting_driver") and (
            code_val in driver_stop_codes or code_val == 0x124):
        drv = windbg_analysis["faulting_driver"]
        p1 = evt.get("p1") or (windbg_analysis.get("bugcheck_p1") if windbg_analysis else None)
        expl = _bc("get_faulting_device_explanation")(drv, code_val, p1, whea_component)
        causes.append(f"  *** FAULTING MODULE: {drv} ***")
        if expl:
            for line in expl.replace(" | ", "\n").split("\n"):
                line = line.strip()
                if line:
                    causes.append(f"  -> {line}")

    # WHEA hardware component (for 0x124) - when we have component but no minidump faulting info
    if code_val == 0x124 and whea_component and not (
            is_most_recent and dump_matches and windbg_analysis and windbg_analysis.get("faulting_driver")
    ):
        causes.append(f"  *** HARDWARE COMPONENT: {whea_component} ***")
        causes.append("  Action: Check this component - update firmware, check temps, test hardware.")

    # Thermal events near crash
    for te in thermal_events[:5]:
        if _match_event_to_crash(te["time"], [evt_time], _bc("_THERMAL_NEAR_CRASH_WINDOW_MIN")):
            causes.append("  *** THERMAL EVENT DETECTED near crash time ***")
            causes.append("  Action: Check cooling, clean fans, improve airflow, monitor temps.")
            break

    for lk in (reliability_ctx or {}).get("livekernel", [])[:8]:
        if _match_event_to_crash(lk.get("time", ""), [evt_time], _bc("_RELIABILITY_NEAR_CRASH_WINDOW_MIN")):
            summary = lk.get("summary") or "Live kernel event"
            causes.append("  *** LIVE KERNEL EVENT near crash time ***")
            causes.append(f"  -> {summary}")
            hint = _summarize_livekernel_message(
                lk.get("summary") or lk.get("message") or "", lk.get("id"),
            )
            low = hint.lower()
            if any(x in low for x in ("graphics", "display", "gpu")):
                causes.append("  Action: Update graphics driver — see Action Plan steps.")
            elif any(x in low for x in ("storage", "disk", "nvme")):
                causes.append("  Action: Update storage/NVMe drivers — see Action Plan steps.")
            else:
                causes.append(f"  Action: Address {hint} — see Action Plan steps.")
            break

    if code_val == 0x124:
        p1 = evt.get("p1")
        p1_int = _parse_p1(str(p1)) if p1 is not None else None
        if p1_int is not None and p1_int in _bc("WHEA_P1_SOURCE"):
            causes.append(f"  WHEA 0x124: {_bc('WHEA_P1_SOURCE')[p1_int]}")
        else:
            causes.append("  WHEA 0x124: see Action Plan for steps matched to your logs.")
    elif code_val == 0xEA:
        causes.append("  Display driver hung: follow Action Plan graphics driver steps.")
    elif code_val in (0x0A, 0xD1):
        causes.append("  Driver IRQL error: update or roll back the driver named in the dump (Action Plan).")

    if (
        is_most_recent
        and dump_matches
        and windbg_analysis
        and not windbg_analysis.get("faulting_driver")
        and windbg_analysis.get("kernel_stack_top")
    ):
        hint = windbg_analysis["kernel_stack_top"]
        causes.append(f"  *** KERNEL STACK TOP: {hint} ***")
        expl = _bc("get_faulting_device_explanation")(
            hint.replace(".exe", "").replace(".sys", ""),
            code_val,
            evt.get("p1"),
            whea_component,
        )
        if expl:
            for line in expl.replace(" | ", "\n").split("\n"):
                line = line.strip()
                if line:
                    causes.append(f"  -> {line}")
    return causes


def _analysis_confidence_label(windbg_analysis: dict | None, has_bugcheck: bool) -> str:
    """Return a short confidence label for novice-facing output."""
    if not windbg_analysis:
        return "Limited — no minidump analyzed (event log only)."
    dumps = windbg_analysis.get("dumps_analyzed", 1)
    recurring = windbg_analysis.get("recurring_faulting_driver")
    if recurring and windbg_analysis.get("recurring_count", 0) >= 2:
        cnt = windbg_analysis["recurring_count"]
        dump_word = "dump" if dumps == 1 else "dumps"
        return f"Very likely — the same faulting module appeared in {cnt} of {dumps} recent {dump_word}."
    if windbg_analysis.get("faulting_driver"):
        dump_word = "dump" if dumps == 1 else "dumps"
        return f"Likely — faulting module identified from the minidump ({dumps} {dump_word} analyzed)."
    if has_bugcheck:
        return "Moderate — stop code from event log; minidump did not name a driver."
    return "Limited — unexpected shutdown with no stop code in the log."


def build_crash_confidence_summary(
    events: list,
    windbg_analysis: dict | None,
    *,
    driver_verification: dict | None = None,
    needs_config: bool = False,
    has_bugcheck: bool = False,
) -> dict:
    """Three-level confidence ladder for Summary / Quick Answer (novice-facing)."""
    drv_ver = driver_verification or {}
    attr = drv_ver.get("attribution") or {}
    dump_matches = attr.get("dump_matches_latest")
    if dump_matches is None:
        dump_matches = _dump_matches_recent_events(windbg_analysis, events)
    can_name = bool(
        attr.get("can_name_faulting_driver")
        or (dump_matches and windbg_analysis and windbg_analysis.get("faulting_driver"))
    )
    platform_focus = bool(attr.get("platform_chipset_focus"))
    faulting = (windbg_analysis or {}).get("faulting_driver") if can_name else None

    if can_name and faulting:
        level = "verified"
        headline = "Verified — minidump names a faulting driver"
        detail = f"The latest incident matches a minidump; faulting module: {faulting}."
    elif platform_focus or (events and not can_name):
        level = "focus"
        headline = "Focus area — no single faulting .sys for the latest incident"
        focus = "AMD/Intel Chipset / Platform drivers"
        if attr.get("lines"):
            for ln in attr["lines"]:
                if "Crash-linked focus:" in ln:
                    focus = ln.split("Crash-linked focus:", 1)[-1].strip().rstrip(".")
                    break
        detail = (
            f"Windows logged a shutdown or boot problem without a matching minidump. "
            f"Crash-linked focus: {focus}."
        )
    elif events:
        level = "moderate"
        headline = "Moderate — crash logged but driver not confirmed"
        detail = _analysis_confidence_label(windbg_analysis, has_bugcheck)
    else:
        level = "unknown"
        headline = "No recent crash events in targeted logs"
        detail = "Run analysis as Administrator after the next incident."

    what_changes: list[str] = []
    if not can_name and events:
        what_changes.append(
            "A minidump from the same time as the latest shutdown/BSOD would name the faulting .sys file."
        )
    if needs_config:
        what_changes.append(
            "Enable memory dumps (Settings or Advanced tab) so the next crash writes a minidump."
        )
    elif _ba("is_user_admin")() and not needs_config and not can_name and events:
        what_changes.append(
            "Memory dumps are enabled — if another crash occurs, re-run analysis to match a new minidump."
        )
    if platform_focus:
        what_changes.append(
            "Verify the chipset/platform suite and its bundled INF components on the Drivers tab."
        )

    lines = [f"CONFIDENCE: {headline}", detail]
    if what_changes:
        lines.append("What would change this:")
        lines.extend(f"  • {w}" for w in what_changes)

    return {
        "level": level,
        "headline": headline,
        "detail": detail,
        "what_would_change": what_changes,
        "lines": lines,
        "can_name_faulting_driver": can_name,
        "platform_chipset_focus": platform_focus,
    }
