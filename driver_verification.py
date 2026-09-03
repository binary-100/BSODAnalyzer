"""Crash-linked driver verification pipeline (Phases 2–6).

See docs/DRIVER_VERIFICATION_PLAN.md and starter pack PHASED_FEATURE_DESIGN.md.
"""

from __future__ import annotations

import json
import re
from typing import Any

import device_enrichment as de
import log_read_windows as lrw
import bsod_crash_report as crash
from bsod_hardware_wmi import CHIPSET_DEVICE_AMD, CHIPSET_DEVICE_INTEL

CONFIDENCE_CONFIRMED = "Confirmed"
CONFIDENCE_LIKELY = "Likely"
CONFIDENCE_SPECULATIVE = "Speculative"

_CONF_RANK = {
    CONFIDENCE_CONFIRMED: 0,
    CONFIDENCE_LIKELY: 1,
    CONFIDENCE_SPECULATIVE: 2,
}

_CATALOG_YES = "yes"
_CATALOG_LIMITED = "limited"
_CATALOG_NO = "no"

_BOOT_DRIVER_HINTS = (
    ("storage", ("storport", "stornvme", "nvme", "iaStor", "amd_sata")),
    ("chipset", ("amdpsp", "amdxhc", "amd_gpio", "intelppm", "iaLPSS")),
    ("graphics", ("nvlddmkm", "amdkmdag", "igdkmd")),
    ("network", ("mt76", "rtwl", "killer", "e2f")),
)

_BAD_VERSIONS = frozenset({"", "?", "0.0.0.0", "0.0.0.1", "10.0.0.0", "—"})


def _norm_module(name: str | None) -> str:
    base = (name or "").strip().lower()
    for suf in (".sys", ".dll", ".exe"):
        if base.endswith(suf):
            base = base[: -len(suf)]
    return base.strip()


def _merge_suspect(
    suspects: dict[str, dict],
    module: str,
    *,
    confidence: str,
    source: str,
) -> None:
    mod = _norm_module(module)
    if not mod:
        return
    key = mod
    entry = suspects.get(key)
    if entry is None:
        suspects[key] = {
            "module": mod,
            "confidence": confidence,
            "sources": [source],
        }
        return
    if _CONF_RANK.get(confidence, 9) < _CONF_RANK.get(entry["confidence"], 9):
        entry["confidence"] = confidence
    if source not in entry["sources"]:
        entry["sources"].append(source)


_HEURISTIC_KERNEL_MODULES = frozenset({
    "storport", "stornvme", "ndis", "ntoskrnl", "nt", "ntkrnlmp", "hal",
    "driver_class", "boot_path",
})

_PLATFORM_CHIPSET_LABELS = {
    "__chipset_amd_platform__": "AMD Chipset / Platform drivers",
    "__chipset_intel_platform__": "Intel Chipset / Platform drivers",
}

_COMPONENT_ROLES_AMD: dict[str, str] = {
    "PSP": "Security processor (platform security / fTPM support)",
    "SMBus": "Motherboard sensor and power communication",
    "GPIO": "On-board connections for sensors and buttons",
    "I2C": "Low-level device bus on the motherboard",
    "MicroPEP": "Power-management helper for AMD platform",
    "PPM": "CPU power management",
    "USB3": "USB 3.x controller",
    "SATA": "SATA storage controller",
    "Other": "Other platform driver in the AMD suite",
}

_COMPONENT_ROLES_INTEL: dict[str, str] = {
    "Chipset INF": "Main Intel chipset driver package",
    "Serial IO": "Serial I/O (touchpad, sensors on Intel boards)",
    "SMBus": "Motherboard sensor and power communication",
    "MEI": "Intel Management Engine interface",
    "Other": "Other platform driver in the Intel suite",
}


def _component_role(label: str, vendor: str) -> str:
    roles = _COMPONENT_ROLES_AMD if vendor == "amd" else _COMPONENT_ROLES_INTEL
    return roles.get(label, "Part of the platform driver suite")


def _is_misleading_kernel_fault_module(driver: str | None) -> bool:
    """True when the dump names ntoskrnl/hal/etc. — not an installable driver row."""
    base = _norm_module(driver or "")
    if not base:
        return False
    return base in crash._MISLEADING_FAULT_MODULES


def _windows_servicing_action_steps(ext_attr: dict | None) -> list[str]:
    hints = (ext_attr or {}).get("cbs_hints") or []
    steps: list[str] = []
    if not hints:
        return steps
    if any("pending restart" in (h.get("category") or "").lower() for h in hints):
        steps.append(
            "Finish pending Windows Update / servicing installs and reboot before chasing "
            "individual drivers — CBS logs show a restart is waiting."
        )
    else:
        steps.append(
            "Check Settings → Windows Update for quality/cumulative updates — CBS logged "
            "component servicing activity near this incident."
        )
    return steps


def _narrative_what_failed_no_dump(latest_date: str) -> str:
    date_bit = latest_date or "the latest incident"
    return (
        f"Windows did not save a minidump for this shutdown, so the crash record does not name a single "
        f"faulting driver file for {date_bit}. That is a logging gap, not a failed analysis — "
        "the fix plan below is the correct troubleshooting path for this pattern on your system."
    )


def _narrative_what_failed_wer(mod: str, src: str, latest_date: str) -> str:
    date_bit = latest_date or "the latest incident"
    return (
        f"Windows Error Reporting ({src}) archived a report suggesting {mod} near {date_bit}. "
        "That is a directed lead from WER, not minidump !analyze — check matching rows on "
        "Drivers -> Needs attention."
    )


def _narrative_why_this_order(
    *,
    wf_status: str,
    faulting: str | None,
    boot_near: bool,
    vendor: str,
    repair_targets: list[dict],
    latest_date: str,
    latest_wer: list[dict],
    evts: list,
    boot_recovery: list | None = None,
) -> str:
    if wf_status == "verified":
        if _is_misleading_kernel_fault_module(faulting):
            return (
                "The minidump names the Windows kernel on the faulting stack — that means "
                "Windows caught a fault, not that ntoskrnl.exe itself is the package to update. "
                "Start with Windows Update, then BIOS/chipset, GPU, storage, and network rows "
                "on Drivers → Needs attention."
            )
        return (
            "The minidump for this incident names the faulting driver — start with that row on "
            "Drivers -> Needs attention."
        )
    if latest_wer:
        mod = latest_wer[0].get("module") or "?"
        return (
            f"Windows Error Reporting points to {mod} near this incident. "
            "Check matching device rows first; a minidump from the same time would name the exact .sys file."
        )
    if repair_targets and boot_near:
        if vendor == "amd":
            platform = "AMD platform"
        elif vendor == "intel":
            platform = "Intel platform"
        else:
            platform = "your platform"
        date_bit = latest_date or "this incident"
        return (
            f"Boot/recovery signals on an {platform} — start with the chipset suite and components, "
            "then BIOS, storage, and GPU. We are confident in that sequence. "
            f"A minidump from {date_bit} would name the specific .sys file; until then, follow the rows "
            "above on Drivers -> Needs attention."
        )
    if repair_targets:
        date_bit = latest_date or "the latest incident"
        return (
            f"No minidump for {date_bit} — the crash record cannot name one faulting .sys file. "
            "The rows above are the logical fix path from the logs Windows did capture."
        )
    if evts:
        return (
            "Enable memory dumps and re-run analysis after the next incident for a specific driver name."
        )
    if boot_recovery:
        return (
            "Boot/recovery entries appear in the report (Section 5a) but no crash stop codes — "
            "this PC looks stable in the log window; use the Action Plan only if you are "
            "troubleshooting actual shutdowns or boot loops."
        )
    return "No recent crash events in the logs we checked."


def _narrative_action_steps_from_targets(
    repair_targets: list[dict],
    *,
    wf_status: str,
    faulting: str | None,
    faulting_device: str,
    boot_near: bool,
    windbg_analysis: dict | None = None,
    ext_attr: dict | None = None,
) -> list[str]:
    """5a — Action Plan steps cite exact Drivers -> Needs attention row labels."""
    steps: list[str] = []
    if boot_near and wf_status != "verified":
        steps.append(
            "Follow boot/recovery steps on the Action Plan tab (BIOS, then platform suite, "
            "then storage/GPU)."
        )
    if wf_status == "verified" and faulting:
        if _is_misleading_kernel_fault_module(faulting):
            steps.extend(_windows_servicing_action_steps(ext_attr))
            if boot_near:
                steps.append(
                    "Follow boot/recovery steps on the Action Plan tab (BIOS, then platform suite, "
                    "then storage/GPU)."
                )
            steps.append(
                "Kernel fault on the stack — run ② Search for updates on AMD Chipset / Platform, "
                "GPU, storage, and network rows (not the synthetic ntoskrnl row)."
            )
            stacks = (windbg_analysis or {}).get("stack_frames") or []
            if stacks:
                steps.append(
                    f"Minidump call stack (top): {' → '.join(stacks[:3])} — look for a "
                    "third-party .sys below the kernel if WinDbg lists one."
                )
        else:
            label = next(
                (t["label"] for t in repair_targets if t.get("kind") == "faulting_driver"),
                faulting_device or faulting or "faulting driver",
            )
            steps.append(
                f"Drivers -> Needs attention: update or roll back {label} "
                "(faulting driver for this incident)."
            )
            return steps
    suite = next((t for t in repair_targets if t.get("kind") == "chipset_suite"), None)
    if suite:
        ver = f" (installed {suite['version']})" if suite.get("version") else ""
        steps.append(
            f"Drivers -> Needs attention: check for updates to {suite['label']}{ver}."
        )
    components = sorted(
        [t for t in repair_targets if t.get("kind") == "chipset_component"],
        key=lambda t: int(t.get("priority") or 99),
    )
    for comp in components[:8]:
        ver = f" (installed {comp['version']})" if comp.get("version") else ""
        steps.append(
            f"Drivers -> Needs attention: run Search for updates on {comp['label']}{ver}."
        )
    for dev in repair_targets:
        if dev.get("kind") != "mapped_device":
            continue
        ver = f" (installed {dev['version']})" if dev.get("version") else ""
        steps.append(
            f"Drivers -> Needs attention: run Search for updates on {dev['label']}{ver}."
        )
    return steps


def build_crash_repair_narrative(
    events: list,
    windbg_analysis: dict | None,
    *,
    boot_recovery: list | None = None,
    system_ctx: dict | None = None,
    bios_driver_info: dict | None = None,
    attribution: dict | None = None,
    suspects: list[dict] | None = None,
    culprit_device_names: set | None = None,
) -> dict[str, Any]:
    """End-user narrative: what happened, what failed, what to check (concrete device rows)."""
    ctx = system_ctx or {}
    attr = attribution or {}
    boot = boot_recovery or []
    evts = events or []
    dump_matches = crash._dump_matches_recent_events(windbg_analysis, evts)
    incidents = crash._group_events_by_incident(evts)
    latest = incidents[0] if incidents else []
    latest_time = latest[0].get("time", "?") if latest else "?"
    latest_date = latest_time[:10] if latest_time and len(latest_time) >= 10 else latest_time
    code_val, stop_name, stop_desc, latest_verified = (
        crash._verified_stop_for_incident(latest, windbg_analysis, events=evts)
        if latest else (None, "", "", False)
    )
    crash_times = [e.get("time", "") for e in latest if e.get("time")]
    boot_near = bool(crash.boot_events_near_crash(boot, crash_times, window_minutes=15))

    faulting = None
    faulting_device = ""
    if dump_matches and windbg_analysis:
        faulting = windbg_analysis.get("faulting_driver")
        for s in suspects or []:
            mod = _norm_module(s.get("module"))
            if mod and faulting and _norm_module(faulting) == mod:
                devs = s.get("devices") or []
                if devs:
                    faulting_device = (devs[0].get("name") or "").strip()
                break

    # --- What happened ---
    if latest_verified and stop_name:
        friendly_stop = stop_name.replace("_", " ")
        what_happened = (
            f"Windows stopped with a blue screen on {latest_date or latest_time} "
            f"({friendly_stop})."
        )
    elif latest and boot_near:
        what_happened = (
            f"Your PC shut down unexpectedly on {latest_date or latest_time}. "
            "Windows also logged boot or recovery activity around that time — "
            "typical of a startup or boot-path problem rather than a fully logged blue-screen crash."
        )
    elif latest:
        what_happened = (
            f"Your PC shut down unexpectedly on {latest_date or latest_time}. "
            "Windows did not record a verified blue-screen stop code for that event."
        )
    elif evts:
        what_happened = "Windows logged crash-related activity in the event log."
    elif boot:
        boot_when = (boot[0].get("time") or "")[:10] if boot else ""
        when_bit = f" on {boot_when}" if boot_when else ""
        what_happened = (
            "No blue-screen or unexpected-shutdown events in the log window we checked."
            f" Windows logged boot activity{when_bit} (see Boot & recovery) — "
            "normal startup logging, not evidence of a crash on this PC."
        )
    else:
        what_happened = "No recent crash or shutdown events were found in the logs we checked."

    # --- What failed ---
    older_note = ""
    ext_attr = ctx.get("extended_log_attribution") or {}
    latest_wer = [
        h for h in (ext_attr.get("latest_incident_wer_hints") or [])
        if not h.get("historical") and h.get("module")
    ]
    if faulting and dump_matches:
        wf_status = "verified"
        if _is_misleading_kernel_fault_module(faulting):
            stacks = (windbg_analysis or {}).get("stack_frames") or []
            stack_bit = (
                f" Stack: {' → '.join(stacks[:3])}." if stacks else ""
            )
            what_failed_summary = (
                f"The minidump faulting module is {faulting} — Windows caught a fault in "
                f"kernel code; that usually points to a driver, firmware, memory, or Windows "
                f"servicing issue underneath, not a missing ntoskrnl package.{stack_bit}"
            )
        else:
            dev_bit = f" ({faulting_device})" if faulting_device else ""
            what_failed_summary = (
                f"The crash dump for this incident points to driver file {faulting}{dev_bit}."
            )
    elif windbg_analysis and not dump_matches:
        wf_status = "unknown"
        if latest_wer:
            mod = latest_wer[0]["module"]
            src = latest_wer[0].get("wer_source") or "WER report"
            what_failed_summary = _narrative_what_failed_wer(mod, src, latest_date)
        else:
            what_failed_summary = _narrative_what_failed_no_dump(latest_date)
        latest_date = latest_time[:10] if latest_time and len(latest_time) >= 10 else latest_time
        older_note = lrw.build_stale_dump_note(
            windbg_analysis,
            latest_incident_date=latest_date,
        )
        if not older_note:
            old_drv = windbg_analysis.get("faulting_driver") or windbg_analysis.get("kernel_stack_top") or ""
            dump_t = windbg_analysis.get("dump_time") or "?"
            if old_drv:
                older_note = (
                    f"Separate note: an older crash dump from {dump_t[:10] if dump_t else dump_t} "
                    f"mentioned {old_drv}. That is a different incident unless a new dump matches this date."
                )
    else:
        wf_status = "unknown"
        if latest_wer:
            mod = latest_wer[0]["module"]
            src = latest_wer[0].get("wer_source") or "WER report"
            what_failed_summary = _narrative_what_failed_wer(mod, src, latest_date)
        else:
            what_failed_summary = _narrative_what_failed_no_dump(latest_date)

    # --- Repair targets ---
    repair_targets: list[dict[str, str]] = []
    vendor = "amd" if ctx.get("has_amd_chipset") else ("intel" if ctx.get("has_intel_chipset") else "")

    if wf_status == "verified" and faulting and not _is_misleading_kernel_fault_module(faulting):
        repair_targets.append({
            "label": faulting_device or crash._friendly_driver_label(faulting),
            "device_name": faulting_device or "",
            "role": f"Driver file that crashed: {faulting}",
            "version": "",
            "priority": "1",
            "kind": "faulting_driver",
        })

    suite_label = "AMD Chipset Software" if vendor == "amd" else (
        "Intel Chipset Driver" if vendor == "intel" else ""
    )
    platform_focus = bool(attr.get("platform_chipset_focus"))
    kernel_fault = bool(
        wf_status == "verified"
        and faulting
        and _is_misleading_kernel_fault_module(faulting)
    )
    if suite_label and (
        platform_focus
        or kernel_fault
        or (not dump_matches and vendor and boot_near)
    ):
        suite_ver = ""
        try:
            import driver_catalog as dc

            inv = crash.device_inventory_for_matching(bios_driver_info)
            suite_ver = dc._load_chipset_suite_installed_version(vendor) or ""
            comps = dc._collect_chipset_bundle_components(vendor, inv)
            if suite_ver:
                repair_targets.append({
                    "label": suite_label,
                    "device_name": CHIPSET_DEVICE_AMD if vendor == "amd" else CHIPSET_DEVICE_INTEL,
                    "role": "Main platform driver package (install/update this first)",
                    "version": suite_ver,
                    "priority": "1" if wf_status != "verified" else "2",
                    "kind": "chipset_suite",
                })
            for i, c in enumerate(comps[:8]):
                repair_targets.append({
                    "label": c.get("label") or "?",
                    "device_name": c.get("device_name") or "",
                    "role": _component_role(c.get("label") or "", vendor),
                    "version": c.get("version") or "",
                    "priority": str(i + 2),
                    "kind": "chipset_component",
                })
        except Exception as exc:
            try:
                import session_log

                session_log.progress(
                    "driver_verification",
                    f"repair target chipset row: {type(exc).__name__}",
                    extra={"status": "skip"},
                )
            except Exception:
                pass  # optional session_log; must not break verification path

    seen_targets: set[str] = set()
    for s in suspects or []:
        if s.get("map_status") != "mapped":
            continue
        mod = s.get("module") or ""
        if crash.is_platform_chipset_device_key(mod) or mod in _HEURISTIC_KERNEL_MODULES:
            continue
        for dev in s.get("devices") or []:
            name = (dev.get("name") or "").strip()
            if not name or name.lower() in seen_targets:
                continue
            seen_targets.add(name.lower())
            repair_targets.append({
                "label": name,
                "device_name": name,
                "role": f"Crash-linked device ({crash._friendly_driver_label(mod) or mod})",
                "version": dev.get("version") or "",
                "priority": "3",
                "kind": "mapped_device",
            })

    why_this_order = _narrative_why_this_order(
        wf_status=wf_status,
        faulting=faulting,
        boot_near=boot_near,
        vendor=vendor,
        repair_targets=repair_targets,
        latest_date=latest_date,
        latest_wer=latest_wer,
        evts=evts,
        boot_recovery=boot,
    )

    # --- Headline for Summary banner ---
    if wf_status == "verified" and faulting:
        if _is_misleading_kernel_fault_module(faulting):
            headline = "Kernel fault — likely driver, firmware, or Windows servicing"
        else:
            headline = f"Driver crash: {crash._friendly_driver_label(faulting)}"
        subtitle = what_happened
    elif latest and boot_near:
        headline = f"Unexpected shutdown / boot problem — {latest_date or 'recent'}"
        subtitle = "Check platform software and firmware on the Action Plan tab."
    elif latest:
        headline = f"Unexpected shutdown — {latest_date or 'recent'}"
        subtitle = "No verified blue-screen code for this incident."
    elif boot:
        headline = "No crashes in log window — boot activity only"
        subtitle = (
            "Windows logged normal startup events (Boot & recovery). "
            "No action needed unless the PC is unstable."
        )
    else:
        headline = "No recent crashes in log window"
        subtitle = ""

    action_steps = _narrative_action_steps_from_targets(
        repair_targets,
        wf_status=wf_status,
        faulting=faulting,
        faulting_device=faulting_device,
        boot_near=boot_near,
        windbg_analysis=windbg_analysis,
        ext_attr=ext_attr,
    )
    ext = ctx.get("extended_log_attribution") or {}
    for step in ext.get("action_steps") or []:
        if step and step not in action_steps:
            action_steps.append(step)

    context_notes = list(ext.get("context_lines") or [])

    return {
        "headline": headline,
        "subtitle": subtitle,
        "what_happened": what_happened,
        "what_failed": {
            "status": wf_status,
            "summary": what_failed_summary,
            "driver_file": faulting if wf_status == "verified" else None,
            "device_name": faulting_device or None,
        },
        "repair_targets": repair_targets,
        "older_incident_note": older_note,
        "context_notes": context_notes,
        "why_this_order": why_this_order,
        "action_steps": action_steps,
        "dump_matches_latest": dump_matches,
    }


def format_repair_narrative_quick_answer(narrative: dict | None) -> list[str]:
    """Plain Quick Answer lines from repair narrative (export / CLI)."""
    n = narrative or {}
    lines: list[str] = []
    if n.get("what_happened"):
        lines.append("  WHAT HAPPENED:")
        lines.append(f"    {n['what_happened']}")
        lines.append("")
    wf = n.get("what_failed") or {}
    if wf.get("summary"):
        lines.append("  WHAT FAILED (THIS INCIDENT):")
        lines.append(f"    {wf['summary']}")
        lines.append("")
    targets = n.get("repair_targets") or []
    if targets:
        lines.append("  WHAT TO CHECK ON YOUR PC:")
        for t in targets[:10]:
            ver = f" — installed {t['version']}" if t.get("version") else ""
            role = t.get("role") or ""
            label = t.get("label") or "?"
            lines.append(f"    • {label}{ver}")
            if role:
                lines.append(f"      ({role})")
        lines.append("")
    why = n.get("why_this_order") or n.get("how_sure")
    if why:
        lines.append(f"  WHY THIS ORDER:")
        lines.append(f"    {why}")
        lines.append("")
    if n.get("older_incident_note"):
        lines.append(f"  {n['older_incident_note']}")
        lines.append("")
    for note in n.get("context_notes") or []:
        lines.append(f"  {note}")
        lines.append("")
    return lines


def _boot_path_module_hints(
    boot_recovery: list,
    *,
    system_ctx: dict | None = None,
    platform_chipset_focus: bool = False,
) -> list[tuple[str, str]]:
    hints: list[tuple[str, str]] = []
    if not boot_recovery:
        return hints
    text = " ".join(
        (e.get("message") or e.get("note") or "").lower()
        for e in boot_recovery[:8]
    )
    ctx = system_ctx or {}
    if platform_chipset_focus or ctx.get("has_amd_chipset") or ctx.get("has_intel_chipset"):
        hints.append(("platform_chipset", "boot/recovery — platform/chipset path"))
        if platform_chipset_focus:
            return hints
    if any(w in text for w in ("storage", "disk", "nvme", "boot device")):
        hints.extend((m, "boot/recovery — storage path") for m in _BOOT_DRIVER_HINTS[0][1])
    if any(w in text for w in ("video", "display", "graphics", "gpu")):
        hints.extend((m, "boot/recovery — graphics path") for m in _BOOT_DRIVER_HINTS[2][1])
    if not hints:
        hints.append(("platform_chipset", "boot/recovery — generic boot path"))
    return hints


def _kernel_expansion_modules(
    windbg_analysis: dict | None,
    *,
    dump_matches: bool,
) -> list[tuple[str, str]]:
    if not dump_matches or not windbg_analysis:
        return []
    stack = windbg_analysis.get("stack_frames") or []
    top = (windbg_analysis.get("kernel_stack_top") or windbg_analysis.get("faulting_driver") or "")
    kernel_only = bool(
        top
        and _norm_module(top) in ("ntoskrnl", "nt", "ntkrnlmp", "hal")
        and not windbg_analysis.get("faulting_driver")
    ) or (
        top
        and _norm_module(top) in ("ntoskrnl", "nt", "ntkrnlmp")
    )
    if not kernel_only and stack:
        kernel_bases = {"nt", "ntoskrnl", "ntkrnlmp", "hal", "win32k", "dxgkrnl"}
        kernel_only = all(
            _norm_module(f.split("!", 1)[0]) in kernel_bases for f in stack[:3] if f
        )
    if not kernel_only:
        return []
    out: list[tuple[str, str]] = []
    for key in ("ntoskrnl", "storport", "ndis"):
        if key in crash.POSSIBLE_DRIVERS:
            out.append((key, "kernel-only stack — possible underlying driver class"))
    return out[:4]


def build_crash_driver_attribution(
    events: list,
    windbg_analysis: dict | None,
    *,
    boot_recovery: list | None = None,
    culprit_device_names: set | None = None,
    system_ctx: dict | None = None,
    bios_driver_info: dict | None = None,
) -> dict:
    """Plain-language driver attribution for the latest crash incident."""
    lines: list[str] = []
    steps: list[str] = []
    ctx = system_ctx or {}
    culprits = {n.strip().lower() for n in (culprit_device_names or set()) if n}
    dump_matches = crash._dump_matches_recent_events(windbg_analysis, events)
    incidents = crash._group_events_by_incident(events or [])
    latest = incidents[0] if incidents else []
    latest_time = latest[0].get("time", "?") if latest else "?"
    _code, stop_name, _desc, latest_verified = (
        crash._verified_stop_for_incident(latest, windbg_analysis, events=events)
        if latest else (None, "", "", False)
    )

    faulting = None
    if dump_matches and windbg_analysis:
        faulting = windbg_analysis.get("faulting_driver")

    lines.append("DRIVER ATTRIBUTION (latest incident):")
    if faulting:
        lines.append(
            f"  Faulting module: {faulting} (minidump matches latest event at {latest_time})."
        )
        if _is_misleading_kernel_fault_module(faulting):
            steps.extend(_windows_servicing_action_steps(
                (system_ctx or {}).get("extended_log_attribution")
            ))
            steps.append(
                "Kernel stack fault — check Windows Update, then platform/GPU/storage/network "
                "drivers on the Drivers tab (ntoskrnl.exe itself is not a catalog row to update)."
            )
        else:
            steps.append(f"Update or roll back the driver for {faulting} (see Devices tab).")
    elif not dump_matches and windbg_analysis and windbg_analysis.get("faulting_driver"):
        dump_t = windbg_analysis.get("dump_time") or "?"
        old_drv = windbg_analysis["faulting_driver"]
        lines.append(
            f"  Latest event ({latest_time}): no minidump — a single faulting .sys cannot be named."
        )
        lines.append(
            f"  Older minidump ({dump_t}): {old_drv} — treat as a separate incident, not this shutdown."
        )
    else:
        lines.append(
            f"  Latest event ({latest_time}): no minidump — a single faulting .sys cannot be named."
        )

    platform_labels: list[str] = []
    for key in culprits:
        if crash.is_platform_chipset_device_key(key):
            platform_labels.append(_PLATFORM_CHIPSET_LABELS.get(key, key))
    if platform_labels:
        lines.append(
            "  Crash-linked focus: " + "; ".join(platform_labels) + "."
        )
        steps.insert(
            0,
            "Check AMD/Intel Chipset / Platform drivers on the Drivers tab (suite + bundle components).",
        )
        try:
            import driver_catalog as dc

            inv = crash.device_inventory_for_matching(bios_driver_info)
            vendor = ""
            if ctx.get("has_amd_chipset"):
                vendor = "amd"
            elif ctx.get("has_intel_chipset"):
                vendor = "intel"
            if vendor and inv:
                comps = dc._collect_chipset_bundle_components(vendor, inv)
                if comps:
                    comp_labels = ", ".join(
                        f"{c.get('label') or '?'} {c.get('version') or '?'}" for c in comps[:8]
                    )
                    lines.append(f"  Installed bundle components: {comp_labels}.")
                    short = ", ".join(c.get("label") or "?" for c in comps[:6])
                    if steps:
                        steps[0] = (
                            f"Verify chipset/platform suite components on Drivers tab: {short}."
                        )
        except Exception as exc:
            try:
                import session_log

                session_log.progress(
                    "driver_verification",
                    f"chipset bundle lookup: {type(exc).__name__}",
                    extra={"status": "skip"},
                )
            except Exception:
                pass  # optional session_log; must not break verification path
    elif boot_recovery and not dump_matches:
        lines.append(
            "  Boot/recovery pattern: prioritize BIOS, chipset/platform suite, then storage and GPU drivers."
        )

    if boot_recovery and not dump_matches and not faulting:
        if not steps:
            steps.append(
                "Review Section 5a (Boot & recovery); update BIOS, chipset platform suite, NVMe/GPU drivers."
            )
        lines.append(
            "  Do not treat inbox Microsoft storage stack drivers (storport/disk class) as the crash culprit."
        )

    if latest_verified and stop_name:
        lines.append(f"  Verified stop code for latest incident: {stop_name.replace('_', ' ')}.")
    elif latest and not latest_verified:
        lines.append(
            "  No verified BSOD stop code for the latest shutdown (Event 41 alone is not used)."
        )

    return {
        "lines": lines,
        "action_plan_steps": steps,
        "can_name_faulting_driver": bool(faulting),
        "faulting_driver": faulting,
        "platform_chipset_focus": bool(platform_labels),
        "dump_matches_latest": dump_matches,
    }


def build_crash_suspect_list(
    events: list,
    windbg_analysis: dict | None,
    *,
    boot_recovery: list | None = None,
    code_val: int | None = None,
    stop_name: str = "",
    stop_code_verified: bool = False,
    culprit_device_names: set | None = None,
    system_ctx: dict | None = None,
) -> list[dict]:
    """Phase 2 — ordered suspect modules with link confidence."""
    suspects: dict[str, dict] = {}
    dump_matches = crash._dump_matches_recent_events(windbg_analysis, events)
    culprits = {n.strip().lower() for n in (culprit_device_names or set()) if n}
    platform_focus = any(crash.is_platform_chipset_device_key(n) for n in culprits)

    if windbg_analysis and dump_matches:
        drv = windbg_analysis.get("faulting_driver")
        if drv and crash.has_crash_faulting_driver(drv):
            _merge_suspect(
                suspects, drv, confidence=CONFIDENCE_CONFIRMED, source="minidump faulting module"
            )
        ktop = windbg_analysis.get("kernel_stack_top")
        if ktop and _norm_module(ktop) == "ntoskrnl":
            _merge_suspect(
                suspects, ktop, confidence=CONFIDENCE_LIKELY, source="kernel stack top"
            )
        recurring = windbg_analysis.get("recurring_faulting_driver")
        if recurring and crash.has_crash_faulting_driver(recurring):
            _merge_suspect(
                suspects, recurring, confidence=CONFIDENCE_CONFIRMED, source="recurring minidump module"
            )

    if stop_code_verified and code_val is not None and stop_name:
        if code_val in (0x0A, 0xD1, 0x7E, 0x3B):
            _merge_suspect(
                suspects,
                "driver_class",
                confidence=CONFIDENCE_LIKELY,
                source="IRQL/driver stop code template",
            )

    for mod, src in _boot_path_module_hints(
        boot_recovery or [],
        system_ctx=system_ctx,
        platform_chipset_focus=platform_focus,
    ):
        _merge_suspect(suspects, mod, confidence=CONFIDENCE_LIKELY, source=src)

    for key in culprits:
        if crash.is_platform_chipset_device_key(key) and not dump_matches:
            _merge_suspect(
                suspects,
                key,
                confidence=CONFIDENCE_LIKELY,
                source="crash-linked platform/chipset row",
            )

    if not dump_matches:
        for hint in (system_ctx or {}).get("wer_dump_recovery", {}).get("module_hints") or []:
            mod = hint.get("module")
            if mod and crash.has_crash_faulting_driver(mod):
                _merge_suspect(
                    suspects,
                    mod,
                    confidence=CONFIDENCE_LIKELY,
                    source="WER archived report (minidump missing on disk)",
                )
        ext = (system_ctx or {}).get("extended_log_attribution") or {}
        for hint in ext.get("latest_incident_wer_hints") or []:
            if hint.get("historical"):
                continue
            mod = hint.get("module")
            if not mod or not crash.has_crash_faulting_driver(mod):
                continue
            src_label = hint.get("wer_source") or hint.get("source") or "WER report"
            _merge_suspect(
                suspects,
                mod,
                confidence=CONFIDENCE_LIKELY,
                source=f"WER {src_label} (no minidump for latest incident)",
            )

    if dump_matches:
        for mod, src in _kernel_expansion_modules(windbg_analysis, dump_matches=True):
            _merge_suspect(suspects, mod, confidence=CONFIDENCE_SPECULATIVE, source=src)

    if not dump_matches and platform_focus:
        for mod in list(suspects):
            if mod in _HEURISTIC_KERNEL_MODULES and mod != "platform_chipset":
                suspects.pop(mod, None)

    if not suspects and events:
        _merge_suspect(
            suspects,
            "boot_path",
            confidence=CONFIDENCE_SPECULATIVE,
            source="unexpected shutdown / boot event without named module",
        )

    ordered = sorted(
        suspects.values(),
        key=lambda s: (_CONF_RANK.get(s["confidence"], 9), s["module"]),
    )
    return ordered


def _pnp_by_name(pnp_list: list | None) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for row in pnp_list or []:
        name = (row.get("Name") or "").strip()
        if name:
            out[name.lower()] = row
    return out


def _device_class_hint(module: str) -> str:
    m = _norm_module(module)
    if m in ("driver_class", "boot_path"):
        return "Check Device Manager for devices with a warning icon near the crash time."
    if any(x in m for x in ("nvlddmkm", "amdkmdag", "igdkmd", "dxg")):
        return "Open Device Manager → Display adapters."
    if any(x in m for x in ("storport", "stornvme", "nvme", "iastor", "amd_sata")):
        return "Open Device Manager → Storage controllers / Disk drives."
    if any(x in m for x in ("ndis", "net", "rtwl", "killer", "mt76")):
        return "Open Device Manager → Network adapters."
    if m in ("ntoskrnl", "nt", "ntkrnlmp", "hal"):
        return "Kernel fault — check Display, Storage, Network, and Chipset drivers in Device Manager."
    return "Open Device Manager and review drivers for devices active at boot."


def map_suspects_to_devices(
    suspects: list[dict],
    inventory: list | None,
    *,
    pnp_list: list | None = None,
    system_ctx: dict | None = None,
) -> list[dict]:
    """Phase 3 — attach device names or unmapped status to each suspect."""
    inv = inventory or []
    mapped: list[dict] = []
    for s in suspects:
        mod = s["module"]
        if crash.is_platform_chipset_device_key(mod):
            try:
                from bsod_hardware_wmi import chipset_driver_catalog_entries
            except ImportError:
                chipset_driver_catalog_entries = None  # type: ignore[assignment]
            label = _PLATFORM_CHIPSET_LABELS.get(mod, mod)
            version = "?"
            if chipset_driver_catalog_entries:
                for row in chipset_driver_catalog_entries(system_ctx or {}):
                    if (row.get("name") or "").strip().lower() == mod:
                        label = row.get("display_name") or label
                        version = row.get("version") or "?"
                        break
            entry = dict(s)
            entry["map_status"] = "mapped"
            entry["devices"] = [{
                "name": label,
                "version": version,
                "date": "",
                "device_class": "chipset",
            }]
            mapped.append(entry)
            continue
        if mod == "platform_chipset":
            entry = dict(s)
            entry["map_status"] = "unmapped"
            entry["devices"] = []
            entry["manual_hint"] = (
                "Open Device Manager → System devices (AMD PSP, SMBus, GPIO, I2C) and the "
                "AMD Chipset / Platform drivers row on the Drivers tab."
            )
            mapped.append(entry)
            continue
        if mod in ("driver_class", "boot_path"):
            entry = dict(s)
            entry["map_status"] = "unmapped"
            entry["devices"] = []
            entry["manual_hint"] = _device_class_hint(mod)
            mapped.append(entry)
            continue
        if not crash.has_crash_faulting_driver(mod) and mod not in crash.POSSIBLE_DRIVERS:
            # Heuristic module name (storport hint etc.) — try device class mapping
            names = sorted(crash.find_culprit_devices(inv, mod + ".sys"))
        else:
            driver = mod if mod.endswith((".sys", ".dll")) else mod + ".sys"
            names = sorted(crash.find_culprit_devices(inv, driver))
        devices = []
        for n in names:
            row = crash.lookup_inventory_row(inv, n)
            devices.append({
                "name": n,
                "version": (row or {}).get("version", "?"),
                "date": (row or {}).get("date", ""),
                "device_class": (row or {}).get("device_class", ""),
            })
        entry = dict(s)
        if devices:
            entry["map_status"] = "mapped"
            entry["devices"] = devices
        else:
            entry["map_status"] = "unmapped"
            entry["devices"] = []
            entry["manual_hint"] = _device_class_hint(mod)
        mapped.append(entry)
    return mapped


def _fetch_signed_driver_device_ids(device_names: list[str]) -> dict[str, str]:
    if not device_names:
        return {}
    from bsod_runtime import run_powershell

    safe = [n.replace("'", "''") for n in device_names[:12]]
    joined = ", ".join(f"'{n}'" for n in safe)
    ps = rf"""
    $names = @({joined})
    Get-CimInstance Win32_PnPSignedDriver -ErrorAction SilentlyContinue |
      Where-Object {{ $names -contains $_.DeviceName }} |
      Select-Object DeviceName, DeviceID |
      ConvertTo-Json -Depth 2
    """
    ok, out = run_powershell(ps)
    if not ok or not (out or "").strip():
        return {}
    try:
        data = json.loads(out)
        if isinstance(data, dict):
            data = [data]
        return {
            (r.get("DeviceName") or "").strip().lower(): (r.get("DeviceID") or "").strip()
            for r in data
            if r.get("DeviceName")
        }
    except (json.JSONDecodeError, TypeError):
        return {}


def _normalize_dev_id(dev_id: str) -> str:
    return re.sub(r"\\+", r"\\", (dev_id or "").strip().upper())


def _ids_align(pnp_id: str, signed_id: str) -> bool:
    a = _normalize_dev_id(pnp_id)
    b = _normalize_dev_id(signed_id)
    if not a or not b:
        return True
    if a == b:
        return True
    # Same instance tail after last \
    return a.split("\\")[-1] == b.split("\\")[-1]


def _cross_vendor_mismatch(pnp_row: dict, inv_row: dict | None) -> str | None:
    pnp_name = (pnp_row.get("Name") or "").lower()
    pnp_mfg = (pnp_row.get("Manufacturer") or "").lower()
    inv_name = ((inv_row or {}).get("name") or "").lower()
    hw = de.parse_hardware_ids(pnp_row.get("DeviceID") or "")
    ven = (hw.get("VEN") or "").lower()
    intel_in_pnp = "intel" in pnp_name or "intel" in pnp_mfg or ven == "8086"
    realtek_in_drv = "realtek" in inv_name
    if intel_in_pnp and realtek_in_drv and "audio" not in pnp_name:
        return "Installed driver vendor may not match device hardware (Intel device, Realtek-class driver name)."
    amd_in_pnp = "amd" in pnp_name or "amd" in pnp_mfg or ven == "1022"
    nvidia_in_drv = "nvidia" in inv_name
    if amd_in_pnp and nvidia_in_drv:
        return "Installed driver vendor may not match AMD device."
    return None


def _bad_version(version: str | None) -> bool:
    v = (version or "").strip().lower()
    return v in _BAD_VERSIONS


def verify_suspect_drivers_locally(
    mapped_suspects: list[dict],
    *,
    pnp_list: list | None,
    inventory: list | None,
    problem_devices: list | None,
    generic_devices: list | None,
) -> list[dict]:
    """Phase 4 — local install health for mapped suspects."""
    pnp_index = _pnp_by_name(pnp_list)
    problem_names = {
        (d.get("name") or "").strip().lower() for d in (problem_devices or [])
    }
    generic_names = {
        (d.get("name") or "").strip().lower() for d in (generic_devices or [])
    }
    inv = inventory or []

    device_names = []
    for s in mapped_suspects:
        for d in s.get("devices") or []:
            n = (d.get("name") or "").strip()
            if n:
                device_names.append(n)
    signed_ids = _fetch_signed_driver_device_ids(list(dict.fromkeys(device_names)))

    all_inv_drivers = {
        _norm_module((r.get("name") or ""))
        for r in inv
        if r.get("name")
    }

    verified: list[dict] = []
    for s in mapped_suspects:
        entry = dict(s)
        if s.get("map_status") == "unmapped":
            entry["local"] = {
                "status": "skipped",
                "assessment": "uncertain",
                "checks": [],
                "summary": "Could not map module to a device — manual Device Manager review required.",
            }
            verified.append(entry)
            continue

        checks: list[dict] = []
        assessments: list[str] = []
        mod = s["module"]
        orphan = (
            crash.has_crash_faulting_driver(mod + ".sys")
            and _norm_module(mod) not in all_inv_drivers
            and s.get("confidence") == CONFIDENCE_CONFIRMED
        )
        if orphan:
            checks.append({
                "id": "4f",
                "label": "Module in inventory",
                "result": "fail",
                "detail": f"No installed device row references {mod}.",
            })

        for dev in s.get("devices") or []:
            dname = (dev.get("name") or "").strip()
            key = dname.lower()
            pnp = pnp_index.get(key) or {}
            inv_row = crash.lookup_inventory_row(inv, dname)
            err = int(pnp.get("ConfigManagerErrorCode", 0))
            if err:
                checks.append({
                    "id": "4a",
                    "label": f"Device Manager ({dname})",
                    "result": "fail",
                    "detail": f"ConfigManager error code {err}.",
                })
                assessments.append("bad_install")
            else:
                checks.append({
                    "id": "4a",
                    "label": f"Device Manager ({dname})",
                    "result": "pass",
                    "detail": "No Device Manager error code.",
                })
            if key in generic_names:
                checks.append({
                    "id": "4b",
                    "label": f"Generic driver ({dname})",
                    "result": "fail",
                    "detail": "Device is using a generic or inbox driver.",
                })
                assessments.append("generic_driver")
            else:
                checks.append({
                    "id": "4b",
                    "label": f"Generic driver ({dname})",
                    "result": "pass",
                    "detail": "Not flagged as generic/inbox.",
                })
            pnp_id = pnp.get("DeviceID") or ""
            sig_id = signed_ids.get(key, "")
            if pnp_id and sig_id:
                aligned = _ids_align(pnp_id, sig_id)
                checks.append({
                    "id": "4c",
                    "label": f"HWID alignment ({dname})",
                    "result": "pass" if aligned else "fail",
                    "detail": "PnP and signed-driver DeviceID align."
                    if aligned
                    else "PnP DeviceID does not match signed-driver DeviceID.",
                })
                if not aligned:
                    assessments.append("wrong_driver")
            elif pnp_id:
                checks.append({
                    "id": "4c",
                    "label": f"HWID alignment ({dname})",
                    "result": "unknown",
                    "detail": "Signed-driver DeviceID not returned for comparison.",
                })
            mismatch = _cross_vendor_mismatch(pnp, inv_row)
            if mismatch:
                checks.append({
                    "id": "4d",
                    "label": f"Vendor match ({dname})",
                    "result": "fail",
                    "detail": mismatch,
                })
                assessments.append("cross_vendor")
            if inv_row and _bad_version(inv_row.get("version")):
                checks.append({
                    "id": "4e",
                    "label": f"Version ({dname})",
                    "result": "warn",
                    "detail": f"Suspicious installed version: {inv_row.get('version')!r}.",
                })

        if "bad_install" in assessments:
            assessment = "bad_install"
            summary = "Device Manager reports a driver problem on a crash-linked device."
        elif "wrong_driver" in assessments:
            assessment = "wrong_driver"
            summary = "Installed driver may not match the hardware instance."
        elif "generic_driver" in assessments and "cross_vendor" in assessments:
            assessment = "wrong_driver"
            summary = "Generic or mismatched vendor driver on a crash-linked device."
        elif "generic_driver" in assessments:
            assessment = "generic_driver"
            summary = "Vendor-specific driver recommended for a crash-linked device."
        elif orphan:
            assessment = "uncertain"
            summary = "Crash module not tied to a loaded device row — verify mapping or dump age."
        else:
            assessment = "ok"
            summary = "Installed driver looks present; check for updates if crashes continue."

        entry["local"] = {
            "status": "verified",
            "assessment": assessment,
            "checks": checks,
            "summary": summary,
        }
        verified.append(entry)
    return verified


def gate_catalog_for_suspects(verified_suspects: list[dict]) -> list[dict]:
    """Phase 5 — decide catalog yes / limited / no per suspect."""
    gated: list[dict] = []
    for s in verified_suspects:
        entry = dict(s)
        conf = s.get("confidence") or CONFIDENCE_SPECULATIVE
        local = s.get("local") or {}
        assessment = local.get("assessment") or "uncertain"
        mapped = s.get("map_status") == "mapped"

        if not mapped:
            gate = _CATALOG_NO
            reason = "Unmapped — catalog search would not target a verified device."
        elif conf == CONFIDENCE_SPECULATIVE and assessment in ("ok", "uncertain"):
            gate = _CATALOG_NO
            reason = "Speculative link with no local install problem detected."
        elif conf in (CONFIDENCE_CONFIRMED, CONFIDENCE_LIKELY):
            gate = _CATALOG_YES
            reason = "Crash-linked device mapped with sufficient confidence."
        elif assessment in ("bad_install", "generic_driver", "wrong_driver"):
            gate = _CATALOG_LIMITED
            reason = "Local verification found install issues — catalog may help after mapping is confirmed."
        else:
            gate = _CATALOG_NO
            reason = "Catalog not warranted for this suspect."

        entry["catalog_gate"] = gate
        entry["catalog_gate_reason"] = reason
        entry["catalog"] = {
            "status": "not_run",
            "detail": (
                "Online catalog not run during analysis — use Drivers tab → Check "
                "for crash-linked devices."
                if gate in (_CATALOG_YES, _CATALOG_LIMITED)
                else f"Catalog skipped: {reason}"
            ),
        }
        gated.append(entry)
    return gated


def apply_catalog_results_from_gui(
    verification: dict | None,
    device_catalog_rows: dict[str, dict],
) -> dict | None:
    """Phase 6 — merge GUI catalog check results into verification (when available)."""
    if not verification or not device_catalog_rows:
        return verification
    out = dict(verification)
    suspects = []
    for s in out.get("suspects") or []:
        entry = dict(s)
        if entry.get("catalog_gate") not in (_CATALOG_YES, _CATALOG_LIMITED):
            suspects.append(entry)
            continue
        offers = []
        for dev in entry.get("devices") or []:
            name = (dev.get("name") or "").strip()
            row = device_catalog_rows.get(name.lower())
            if row:
                offers.append(row)
        if offers:
            best = offers[0]
            vs = (best.get("_check_status") or best.get("status") or "").lower()
            hwid = bool(best.get("hwid_matched"))
            if vs in ("newer", "update"):
                detail = f"Update available ({best.get('version') or '?'})"
                if hwid:
                    detail += " — HWID verified."
                entry["catalog"] = {"status": "update_available", "detail": detail, "offers": len(offers)}
            elif vs in ("same", "updated"):
                entry["catalog"] = {"status": "current", "detail": "Installed driver matches or exceeds catalog offer.", "offers": len(offers)}
            else:
                entry["catalog"] = {"status": "checked", "detail": "Catalog checked; see Drivers tab for details.", "offers": len(offers)}
        suspects.append(entry)
    out["suspects"] = suspects
    out["attribution"] = dict((verification or {}).get("attribution") or {})
    return out


def crash_linked_catalog_device_names(
    driver_verification: dict | None,
    culprit_device_names: set | None = None,
    *,
    max_devices: int = 6,
) -> list[str]:
    """Device names for a small post-analysis catalog scan (Phase 6 auto-run)."""
    out: list[str] = []
    seen: set[str] = set()

    def _add(name: str) -> None:
        key = (name or "").strip()
        if not key:
            return
        low = key.lower()
        if low in seen:
            return
        seen.add(low)
        out.append(key)

    culprits = {n.strip().lower() for n in (culprit_device_names or set()) if n}
    for s in (driver_verification or {}).get("suspects") or []:
        if s.get("catalog_gate") not in (_CATALOG_YES, _CATALOG_LIMITED):
            continue
        mod = s.get("module") or ""
        if mod in _PLATFORM_CHIPSET_LABELS or crash.is_platform_chipset_device_key(mod):
            for key in culprits:
                if crash.is_platform_chipset_device_key(key):
                    _add(_PLATFORM_CHIPSET_LABELS.get(key, key))
                    _add(key)
            continue
        if mod == "platform_chipset":
            for key in culprits:
                if crash.is_platform_chipset_device_key(key):
                    _add(_PLATFORM_CHIPSET_LABELS.get(key, key))
                    _add(key)
            continue
        for dev in s.get("devices") or []:
            _add(dev.get("name") or "")

    for key in sorted(culprits):
        if crash.is_platform_chipset_device_key(key):
            _add(_PLATFORM_CHIPSET_LABELS.get(key, key))
            _add(key)

    return out[:max_devices]


def rebuild_verification_report_lines(
    verification: dict | None,
    *,
    attribution: dict | None = None,
) -> dict | None:
    """Rebuild report lines/action steps after catalog merge."""
    if not verification:
        return verification
    attr = attribution or verification.get("attribution") or {}
    return build_driver_verification_report(
        verification.get("suspects") or [],
        attribution=attr if attr.get("lines") else None,
    )


def _overall_confidence(s: dict) -> str:
    conf = s.get("confidence") or CONFIDENCE_SPECULATIVE
    local = s.get("local") or {}
    if s.get("map_status") == "unmapped":
        return "Uncertain"
    if local.get("assessment") == "bad_install" and conf == CONFIDENCE_CONFIRMED:
        return "High"
    if local.get("assessment") in ("wrong_driver", "generic_driver") and conf != CONFIDENCE_SPECULATIVE:
        return "Medium"
    if conf == CONFIDENCE_CONFIRMED and local.get("assessment") == "ok":
        return "High"
    if conf == CONFIDENCE_LIKELY:
        return "Medium"
    return "Uncertain"


def build_driver_verification_report(
    suspects: list[dict],
    *,
    attribution: dict | None = None,
) -> dict:
    """Phase 7 — structured report payload."""
    lines: list[str] = []
    action_hints: list[str] = []
    if attribution:
        lines.extend(attribution.get("lines") or [])
        lines.append("")
        action_hints.extend(attribution.get("action_plan_steps") or [])
    for s in suspects:
        mod = s.get("module") or "?"
        conf = s.get("confidence") or "?"
        src = "; ".join(s.get("sources") or [])
        display_mod = _PLATFORM_CHIPSET_LABELS.get(mod, mod)
        lines.append(f"SUSPECT: {display_mod}")
        lines.append(f"  Link: {_overall_confidence(s)} ({conf}) — {src}")
        if s.get("map_status") == "unmapped":
            lines.append("  Device: (unmapped)")
            lines.append(f"  Manual: {s.get('manual_hint') or 'Device Manager review'}")
        else:
            for dev in s.get("devices") or []:
                lines.append(
                    f"  Device: {dev.get('name')} — installed {dev.get('version') or '?'} "
                    f"({dev.get('device_class') or 'class unknown'})"
                )
        local = s.get("local") or {}
        if local.get("checks"):
            fail = [c for c in local["checks"] if c.get("result") == "fail"]
            if fail:
                lines.append("  Local: " + "; ".join(c["detail"] for c in fail[:3]))
            else:
                lines.append(f"  Local: {local.get('summary') or 'checks passed'}")
        else:
            lines.append(f"  Local: {local.get('summary') or 'n/a'}")
        cat = s.get("catalog") or {}
        lines.append(f"  Catalog: {cat.get('detail') or cat.get('status') or 'n/a'}")
        lines.append(f"  Assessment: {local.get('summary') or 'See above'}")
        lines.append(f"  Confidence: {_overall_confidence(s)}")
        lines.append("")
        assess = local.get("assessment")
        if mod in _HEURISTIC_KERNEL_MODULES:
            continue
        if crash.is_platform_chipset_device_key(mod):
            action_hints.insert(
                0,
                "Verify AMD/Intel Chipset / Platform drivers (suite version + bundle components on Drivers tab).",
            )
            continue
        if assess == "bad_install":
            action_hints.insert(0, f"Fix Device Manager error on crash-linked device for {display_mod}.")
        elif assess in ("wrong_driver", "generic_driver"):
            action_hints.append(
                f"Replace or update driver for crash-linked device ({display_mod}) — vendor driver recommended."
            )
    gated_n = sum(
        1 for s in suspects if s.get("catalog_gate") in (_CATALOG_YES, _CATALOG_LIMITED)
    )
    merged_steps = list(dict.fromkeys(action_hints))
    return {
        "suspects": suspects,
        "lines": lines,
        "action_hints": merged_steps,
        "action_plan_steps": merged_steps,
        "attribution": attribution or {},
        "catalog_gated_count": gated_n,
        "has_suspects": bool(suspects) or bool(attribution),
    }


def verification_action_plan_steps(report: dict | None) -> list[str]:
    if not report:
        return []
    steps = report.get("action_plan_steps") or report.get("action_hints") or []
    return list(steps)


def run_driver_verification_pipeline(
    events: list,
    windbg_analysis: dict | None,
    bios_driver_info: dict | None,
    *,
    pnp_list: list | None,
    problem_devices: list | None,
    generic_devices: list | None,
    boot_recovery: list | None = None,
    culprit_device_names: set | None = None,
    system_ctx: dict | None = None,
) -> dict:
    """Run Phases 2–6 (catalog results merged later from GUI when available)."""
    code_val, stop_name, _stop_desc, has_bc = crash.resolve_crash_code(events, windbg_analysis)
    culprits = {n.strip().lower() for n in (culprit_device_names or set()) if n}
    attribution = build_crash_driver_attribution(
        events,
        windbg_analysis,
        boot_recovery=boot_recovery,
        culprit_device_names=culprits,
        system_ctx=system_ctx,
        bios_driver_info=bios_driver_info,
    )
    suspects = build_crash_suspect_list(
        events,
        windbg_analysis,
        boot_recovery=boot_recovery,
        code_val=code_val,
        stop_name=stop_name,
        stop_code_verified=has_bc,
        culprit_device_names=culprits,
        system_ctx=system_ctx,
    )
    inv = crash.device_inventory_for_matching(bios_driver_info)
    mapped = map_suspects_to_devices(
        suspects, inv, pnp_list=pnp_list, system_ctx=system_ctx
    )
    verified = verify_suspect_drivers_locally(
        mapped,
        pnp_list=pnp_list,
        inventory=inv,
        problem_devices=problem_devices,
        generic_devices=generic_devices,
    )
    gated = gate_catalog_for_suspects(verified)
    narrative = build_crash_repair_narrative(
        events,
        windbg_analysis,
        boot_recovery=boot_recovery,
        system_ctx=system_ctx,
        bios_driver_info=bios_driver_info,
        attribution=attribution,
        suspects=mapped,
        culprit_device_names=culprits,
    )
    report = build_driver_verification_report(gated, attribution=attribution)
    report["repair_narrative"] = narrative
    if narrative.get("action_steps"):
        merged = list(dict.fromkeys(narrative["action_steps"] + (report.get("action_plan_steps") or [])))
        report["action_plan_steps"] = merged
        report["action_hints"] = merged
    return report
