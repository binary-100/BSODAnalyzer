"""Crash fix focus, playbook steps, and platform download links (extracted from bsod_crash_report)."""

from __future__ import annotations

import urllib.parse

from bsod_minidump import minidump_capture_action_step

from crash_report_culprit import _infer_driver_vendor, is_kernel_shim_fault_module


def _bc(name: str):
    """Lazy bsod_crash_report lookup — avoids import cycles during module load."""
    import bsod_crash_report as bc

    return getattr(bc, name)


FIX_CPU_PLATFORM = "cpu_platform"

FIX_GRAPHICS = "graphics"

FIX_STORAGE = "storage"

FIX_NAMED_DRIVER = "named_driver"

FIX_WHEA_COMPONENT = "whea_component"

FIX_THERMAL = "thermal"

FIX_DRIVER_IRQL = "driver_irql"

FIX_MEMORY = "memory"

FIX_UNCERTAIN = "uncertain"

FIX_BOOT_RECOVERY = "boot_recovery"

def build_boot_failure_playbook_steps(
    boot_recovery: list | None,
    *,
    system_ctx: dict | None = None,
    dump_matches_latest: bool = False,
    has_verified_stop: bool = False,
    system_manufacturer: str = "",
    system_model: str = "",
) -> list[str]:
    """Ordered steps when logs show boot/recovery without a verified BSOD stop code."""
    if not boot_recovery or dump_matches_latest or has_verified_stop:
        return []
    ctx = system_ctx or {}
    mfr = (system_manufacturer or ctx.get("system_manufacturer") or "your PC maker").strip()
    model = (system_model or ctx.get("system_model") or "").strip()
    model_bit = f"{mfr} {model}".strip() if _bc("_is_usable_system_model")(model) else mfr
    steps = [
        "Boot/recovery playbook: Windows logged startup repair, Kernel-Boot, or Wininit recovery "
        "— often a failed cold boot before any minidump is written (not a named BSOD stop code).",
        f"Update BIOS/UEFI from {model_bit or mfr} — firmware fixes many cold-boot failures.",
    ]
    if ctx.get("has_amd_chipset") or ctx.get("cpu_vendor") == "amd":
        steps.append(
            "Verify the AMD chipset platform suite and bundled components (PSP, SMBus, GPIO, I2C, PPM) on the Drivers tab."
        )
    elif ctx.get("has_intel_chipset") or ctx.get("cpu_vendor") == "intel":
        steps.append(
            "Verify Intel chipset (INF) platform drivers on the Drivers tab."
        )
    else:
        steps.append(
            "Update chipset/platform drivers from your CPU vendor (AMD or Intel)."
        )
    if ctx.get("has_nvme"):
        steps.append(
            "Update NVMe storage driver/firmware — boot failures often involve the drive the OS boots from."
        )
    if ctx.get("gpu_vendor") or ctx.get("hardware_vendors", {}).get("gpu"):
        steps.append(
            "Update graphics drivers after chipset/BIOS — GPU init runs early in boot."
        )
    steps.append(
        "After changes: full shutdown (not Restart), cold boot, then re-run analysis if problems continue."
    )
    return steps

def derive_report_fix_focus(
    code_val: int | None,
    report_ctx: dict | None,
    faulting_driver: str | None,
    windbg_analysis: dict | None,
    cause_type: dict | None,
    reliability_ctx: dict | None,
    events: list,
    whea_events: list | None,
    thermal_events: list | None,
    *,
    system_ctx: dict | None = None,
) -> dict:
    """Map log/dump evidence to one primary fix path and which download links apply."""
    rc = report_ctx or {}
    p1_int = rc.get("p1_int")
    whea_component = (rc.get("whea_component") or "").strip()
    thermal_near = bool(rc.get("thermal_near"))
    crash_times = rc.get("crash_times") or [e["time"] for e in events if e.get("time")]
    drv = faulting_driver
    drv_base = (drv or "").lower().replace(".sys", "").replace(".dll", "").strip()
    recurring = (windbg_analysis or {}).get("recurring_faulting_driver") if windbg_analysis else None
    ct = cause_type or {}

    gpu_rel = _gpu_relevant_to_crash(
        code_val, p1_int, whea_component, drv, reliability_ctx, crash_times,
    )
    storage_rel = _pcie_storage_relevant(p1_int, whea_component, drv)

    lk_near = False
    lk_topic = ""
    for lk in (reliability_ctx or {}).get("livekernel") or []:
        if _bc("_match_event_to_crash")(lk.get("time", ""), crash_times, _bc("_RELIABILITY_NEAR_CRASH_WINDOW_MIN")):
            lk_near = True
            lk_topic = _bc("_summarize_livekernel_message")(
                lk.get("summary") or lk.get("message") or "", lk.get("id"),
            )
            break

    evidence: list[str] = []
    if recurring:
        evidence.append(f"Minidumps name {recurring} in multiple recent crashes")
    p1_label = rc.get("p1_source_label") or ""
    if code_val == 0x124 and p1_label:
        evidence.append(f"BugCheck 0x124 — {p1_label}")
    if whea_component:
        evidence.append(f"WHEA-Logger reported component: {whea_component}")
    if thermal_near:
        evidence.append("Thermal event logged near the crash time")
    if lk_near and lk_topic:
        evidence.append(f"Live Kernel event near crash: {lk_topic}")

    boot_recovery = (reliability_ctx or {}).get("boot_recovery") or []
    boot_near = any(
        _bc("_match_event_to_crash")(e.get("time", ""), crash_times, _bc("_RELIABILITY_NEAR_CRASH_WINDOW_MIN"))
        for e in boot_recovery[:10]
    )
    if boot_near:
        evidence.append("Boot/recovery events near the latest shutdown")

    focus = FIX_UNCERTAIN
    ctx = system_ctx or {}
    kernel_shim = is_kernel_shim_fault_module(drv)
    if thermal_near and not drv_base and code_val != 0xEA:
        focus = FIX_THERMAL
    elif code_val == 0xEA:
        focus = FIX_GRAPHICS
    elif gpu_rel and not storage_rel:
        focus = FIX_GRAPHICS
    elif storage_rel and not gpu_rel:
        focus = FIX_STORAGE
    elif kernel_shim and (
        ctx.get("has_amd_chipset") or ctx.get("has_intel_chipset") or boot_near
    ):
        focus = FIX_CPU_PLATFORM
    elif drv_base and ct.get("driver_actionable") and drv_base not in _bc("_PLATFORM_CPU_MODULES"):
        focus = FIX_NAMED_DRIVER
    elif drv_base in _bc("_PLATFORM_CPU_MODULES") or (
        code_val == 0x124 and p1_int in (0, 1, None) and not gpu_rel and not storage_rel
    ):
        focus = FIX_CPU_PLATFORM
    elif whea_component:
        focus = FIX_WHEA_COMPONENT
    elif code_val == 0x124 and p1_int == 0x4:
        focus = FIX_STORAGE if storage_rel else (FIX_GRAPHICS if gpu_rel else FIX_CPU_PLATFORM)
    elif code_val in (0x0A, 0xD1) and drv_base:
        if kernel_shim:
            focus = (
                FIX_CPU_PLATFORM
                if ctx.get("has_amd_chipset") or ctx.get("has_intel_chipset")
                else FIX_DRIVER_IRQL
            )
        else:
            focus = FIX_NAMED_DRIVER
    elif code_val in (0x0A, 0xD1):
        focus = FIX_DRIVER_IRQL
    elif code_val in (0x1A, 0x50, 0x7A, 0xC2, 0xC5, 0x109, 0x14E):
        focus = FIX_MEMORY
    elif lk_near:
        low = lk_topic.lower()
        if any(x in low for x in ("graphics", "display", "gpu")):
            focus = FIX_GRAPHICS
        elif any(x in low for x in ("storage", "disk", "nvme")):
            focus = FIX_STORAGE
        elif any(x in low for x in ("network", "usb")):
            focus = FIX_NAMED_DRIVER
    elif code_val == 0x124:
        focus = FIX_CPU_PLATFORM
    elif boot_near and not drv_base and code_val is None:
        ctx = system_ctx or {}
        if ctx.get("has_amd_chipset") or ctx.get("has_intel_chipset"):
            focus = FIX_CPU_PLATFORM
        else:
            focus = FIX_BOOT_RECOVERY

    include_chipset = focus in (FIX_CPU_PLATFORM, FIX_BOOT_RECOVERY)
    include_bios = focus in (FIX_CPU_PLATFORM, FIX_WHEA_COMPONENT, FIX_MEMORY)
    include_oem = focus in (
        FIX_CPU_PLATFORM, FIX_WHEA_COMPONENT, FIX_THERMAL, FIX_MEMORY, FIX_NAMED_DRIVER,
    )

    return {
        "focus": focus,
        "evidence": evidence,
        "include_chipset": include_chipset,
        "include_bios": include_bios,
        "include_oem": include_oem,
        "include_gpu": gpu_rel,
        "include_storage": storage_rel,
        "include_whea_search": bool(whea_component),
        "p1_source_label": p1_label,
        "whea_component": whea_component,
        "lk_near": lk_near,
        "lk_topic": lk_topic,
    }

def build_crash_fix_plan(
    fix_focus: dict,
    *,
    code_val: int | None,
    stop_name: str,
    faulting_driver: str | None,
    windbg_analysis: dict | None,
    system_ctx: dict | None,
    cause_type: dict | None,
    devices_with_generic_driver: list | None = None,
    needs_config: bool = False,
    boot_recovery: list | None = None,
    dump_matches_latest: bool = False,
    has_verified_stop: bool = False,
) -> dict:
    """Ordered fix steps and Action Plan copy from log-derived focus (not generic driver lists)."""
    ctx = system_ctx or {}
    focus = fix_focus.get("focus") or FIX_UNCERTAIN
    evidence = list(fix_focus.get("evidence") or [])
    drv = faulting_driver
    drv_base = (drv or "").lower().replace(".sys", "").replace(".dll", "").strip()
    kernel_shim = is_kernel_shim_fault_module(drv)
    recurring = (windbg_analysis or {}).get("recurring_faulting_driver") if windbg_analysis else None
    mfr = (ctx.get("system_manufacturer") or "your PC maker").strip()
    model = (ctx.get("system_model") or "").strip()
    model_bit = f"{mfr} {model}".strip() if _bc("_is_usable_system_model")(model) else mfr
    platform = _bc("_detected_cpu_platform_label")(ctx)
    p1_label = fix_focus.get("p1_source_label") or ""
    whea_component = fix_focus.get("whea_component") or ""
    steps: list[str] = []
    headline = ""
    links_title = "Downloads for this crash"
    links_intro = "Use these links for the steps above (nothing installs automatically)."

    def _evidence_clause() -> str:
        if evidence:
            return f" (Logs: {evidence[0]})"
        return ""

    boot_steps = build_boot_failure_playbook_steps(
        boot_recovery,
        system_ctx=ctx,
        dump_matches_latest=dump_matches_latest,
        has_verified_stop=has_verified_stop,
        system_manufacturer=mfr,
        system_model=model,
    )

    if focus == FIX_BOOT_RECOVERY and boot_steps:
        headline = "Boot / recovery failure (no BSOD stop code)"
        steps.extend(boot_steps)
        links_title = "BIOS, chipset, and PC maker downloads"

    elif focus == FIX_CPU_PLATFORM:
        if boot_steps and code_val is None and not has_verified_stop:
            headline = "Boot / recovery failure (chipset & platform drivers)"
            steps.extend(boot_steps)
        else:
            if kernel_shim:
                headline = "Kernel fault — likely driver, firmware, or Windows servicing"
            elif code_val == 0x124:
                headline = "CPU / platform hardware error (WHEA)"
            else:
                headline = "CPU / platform hardware error (WHEA)"
            if p1_label:
                headline = f"{headline} — {p1_label}"
            elif code_val == 0x124:
                headline = f"{headline} — uncorrectable hardware error in the System log"
            if ctx.get("has_amd_chipset") or ctx.get("cpu_vendor") == "amd":
                steps.append(
                    "Install the latest AMD chipset drivers for this PC."
                )
            elif ctx.get("has_intel_chipset") or ctx.get("cpu_vendor") == "intel":
                steps.append(
                    "Install the latest Intel chipset (INF) drivers for this PC."
                )
            else:
                steps.append(
                    "Install chipset drivers from your CPU vendor (AMD or Intel)."
                )
            steps.append(
                f"Update BIOS/UEFI from {model_bit or mfr} for your exact model — firmware fixes many CPU/platform WHEA crashes."
            )
            steps.append(
                "Disable CPU overclocking in BIOS; clean fans and vents; let the PC cool before gaming or heavy loads."
            )
            if recurring and recurring != drv and not is_kernel_shim_fault_module(recurring):
                steps.append(
                    f"Also update or roll back {recurring} — it appeared in multiple recent minidumps."
                )
        links_title = "Chipset, BIOS, and PC maker downloads"
        links_intro = (
            "These match the CPU/platform error in your logs — not a full driver scan of every device."
            if code_val == 0x124 or p1_label
            else "These match boot/recovery evidence — start with chipset and BIOS before a full driver scan."
        )

    elif focus == FIX_GRAPHICS:
        headline = "Graphics / display driver problem"
        steps.append(
            "Update or roll back the graphics driver — crash logs point at the GPU or display stack"
            + _evidence_clause()
            + "."
        )
        steps.append(
            "If crashes continue after a clean driver install, check GPU temperature and reseat the card."
        )
        links_title = "Graphics driver downloads"

    elif focus == FIX_STORAGE:
        headline = "Storage / PCIe device hardware error"
        steps.append(
            "Update NVMe/SATA/storage drivers and firmware for the drive on this PC"
            + _evidence_clause()
            + "."
        )
        steps.append(
            "Check cable seating and drive health (CrystalDiskInfo or manufacturer SSD tool)."
        )
        links_title = "Storage driver and firmware downloads"

    elif focus == FIX_NAMED_DRIVER and drv and not is_kernel_shim_fault_module(drv):
        headline = f"Driver fault: {drv}"
        vendor = _infer_driver_vendor(drv_base)
        steps.append(
            f"Update or roll back {drv}"
            + (f" ({vendor})" if vendor else "")
            + " — the minidump or event log names this module"
            + _evidence_clause()
            + "."
        )
        steps.append("Restart the PC after installing; test the same workload that triggered the crash.")
        links_title = f"Downloads for {drv}"

    elif focus == FIX_WHEA_COMPONENT:
        headline = f"Hardware component: {whea_component}"
        steps.append(
            f"Update the driver or firmware for {whea_component} — WHEA-Logger named this component"
            + _evidence_clause()
            + "."
        )
        steps.append(f"Search {mfr} support for BIOS or firmware updates for this PC model.")
        links_title = "Downloads for the reported component"

    elif focus == FIX_THERMAL:
        headline = "Overheating near crash time"
        steps.append(
            "Improve cooling first: clean dust from fans and heatsinks, verify fans spin, improve airflow"
            + _evidence_clause()
            + "."
        )
        steps.append(
            "Reduce load (lower game settings, pause stress tests) until temperatures stay stable under load."
        )
        links_title = "Optional: firmware and drivers after cooling"

    elif focus == FIX_DRIVER_IRQL:
        headline = "Driver conflict (IRQL / memory access)"
        stop_readable = (stop_name or "driver error").replace("_", " ")
        steps.append(
            f"Address the {stop_readable} — usually a third-party driver installed or updated recently."
        )
        if drv and not is_kernel_shim_fault_module(drv):
            steps.append(f"Start with {drv} if you changed that driver lately; otherwise use the newest crash dump driver.")
        elif kernel_shim:
            steps.append(
                "On Drivers → Needs attention, start with chipset/platform rows, then any GPU, storage, "
                "or network driver you updated recently."
            )
        else:
            steps.append(
                "Roll back the most recent driver change (Device Manager → driver → Roll Back), or update GPU/storage/network drivers one at a time."
            )
        links_title = "Driver downloads"

    elif focus == FIX_MEMORY:
        headline = "Possible RAM or memory corruption"
        steps.append(
            "Run Windows Memory Diagnostic (Win+R → mdsched → restart to test RAM)"
            + _evidence_clause()
            + "."
        )
        steps.append(
            "If errors appear, reseat RAM sticks or test one module at a time; update BIOS from your PC maker."
        )
        links_title = "BIOS and PC maker support"

    else:
        headline = "Crash cause not fully identified in logs"
        if code_val is not None and stop_name:
            steps.append(
                f"Investigate stop code {stop_name.replace('_', ' ')} using the evidence listed on the Summary tab."
            )
        links_title = "General support downloads"

    if boot_steps and focus not in (FIX_BOOT_RECOVERY, FIX_CPU_PLATFORM):
        steps[:0] = boot_steps[:2]

    capture_step = minidump_capture_action_step(needs_config=needs_config)
    if capture_step:
        steps.append(capture_step)

    if focus in (FIX_CPU_PLATFORM, FIX_MEMORY, FIX_UNCERTAIN):
        steps.append(
            "If crashes continue after the steps above: run Windows Memory Diagnostic (mdsched.exe)."
        )
    if focus == FIX_UNCERTAIN:
        steps.append(
            "Optional: run sfc /scannow; use DISM /Online /Cleanup-Image /RestoreHealth if the system feels corrupted."
        )
    elif len(steps) <= 5:
        steps.append(
            "Optional: run sfc /scannow only if problems persist after the main fixes above."
        )

    return {
        "focus": focus,
        "headline": headline,
        "evidence": evidence,
        "steps": steps,
        "links_title": links_title,
        "links_intro": links_intro,
        "p1_source_label": fix_focus.get("p1_source_label") or "",
    }

def _needs_platform_driver_links(
    fix_focus: dict | None = None,
    *,
    code_val: int | None = None,
    cause_type: dict | None = None,
    driver: str | None = None,
    thermal_near: bool = False,
    recommendations: list[str] | None = None,
) -> bool:
    """True when Action Plan should show platform/OEM download links for this report."""
    if fix_focus:
        return any(
            fix_focus.get(k)
            for k in (
                "include_chipset",
                "include_bios",
                "include_oem",
                "include_gpu",
                "include_storage",
                "include_whea_search",
            )
        )
    # Legacy fallback if focus not passed
    label = (cause_type or {}).get("label") or ""
    if code_val in (0x124, 0xEA) or code_val in _bc("_HARDWARE_LEAN_STOP_CODES"):
        return True
    if label.startswith(("Hardware", "Platform", "Driver instability")):
        return True
    if thermal_near:
        return True
    drv_base = (driver or "").lower().replace(".sys", "").replace(".dll", "").strip()
    return drv_base in _bc("_PLATFORM_CPU_MODULES") or drv_base in _bc("_MISLEADING_FAULT_MODULES")

def _describe_action_plan_link_basis(
    code_val: int | None,
    report_ctx: dict,
    driver: str | None,
    cause_type: dict | None,
    system_ctx: dict | None,
    reliability_ctx: dict | None = None,
    fix_plan: dict | None = None,
) -> str:
    """One-line tie between download links and log evidence."""
    if fix_plan:
        headline = (fix_plan.get("headline") or "").strip()
        ev = fix_plan.get("evidence") or []
        if headline and ev:
            return f"{headline} — {ev[0]}."
        if headline:
            return headline + "."
        if ev:
            return ev[0] + "."
    return ""

_GPU_DRIVER_FRAGMENTS = frozenset({
    "nvlddmkm", "amdkmdag", "atikmdag", "igdkmd", "igdkmd64", "dxgkrnl", "dxgmms", "dxgmms2",
})

def _gpu_relevant_to_crash(
    code_val: int | None,
    p1_int: int | None,
    whea_component: str,
    faulting_driver: str | None,
    reliability_ctx: dict | None,
    crash_times: list[str],
) -> bool:
    """Only offer GPU vendor download links when logs/dump implicate graphics/PCIe-GPU."""
    if code_val == 0xEA:
        return True
    if p1_int == 0x4:
        return True
    drv_base = (faulting_driver or "").lower().replace(".sys", "").replace(".dll", "").strip()
    if drv_base and any(k in drv_base for k in _GPU_DRIVER_FRAGMENTS):
        return True
    wc = (whea_component or "").lower()
    if any(x in wc for x in ("gpu", "display", "graphics", "nvidia", "radeon", "geforce")):
        return True
    for lk in (reliability_ctx or {}).get("livekernel") or []:
        if not _bc("_match_event_to_crash")(lk.get("time", ""), crash_times, _bc("_RELIABILITY_NEAR_CRASH_WINDOW_MIN")):
            continue
        m = (lk.get("summary") or lk.get("message") or "").lower()
        if "display" in m or "dxg" in m or "gpu" in m or "graphics" in m:
            return True
    return False

def _pcie_storage_relevant(
    p1_int: int | None,
    whea_component: str,
    faulting_driver: str | None,
) -> bool:
    if p1_int == 0x4:
        return True
    wc = (whea_component or "").lower()
    if any(x in wc for x in ("nvme", "storage", "disk", "ssd", "sata", "scsi")):
        return True
    drv_base = (faulting_driver or "").lower().replace(".sys", "")
    return any(x in drv_base for x in ("nvme", "storahci", "stornvme", "iastor", "rst", "nvstor"))

def build_platform_update_options(
    system_ctx: dict | None,
    *,
    code_val: int | None = None,
    report_ctx: dict | None = None,
    faulting_driver: str | None = None,
    bios_driver_info: dict | None = None,
    reliability_ctx: dict | None = None,
    crash_times: list[str] | None = None,
    fix_focus: dict | None = None,
) -> list[dict]:
    """Download links that match this crash's log-derived fix focus (not every device on the PC)."""
    ctx = _bc("_system_ctx_with_service_tag")(system_ctx, bios_driver_info)
    rc = report_ctx or {}
    p1_int = rc.get("p1_int")
    whea_component = rc.get("whea_component") or ""
    p1_label = rc.get("p1_source_label") or ""
    bios_note = _bc("_installed_bios_summary")(bios_driver_info)
    report_prefix = ""
    if code_val == 0x124 and p1_label:
        report_prefix = f"From this crash report (WHEA): {p1_label}. "
    elif whea_component:
        report_prefix = f"From this crash report (WHEA component): {whea_component}. "

    ff = fix_focus or {}
    times = crash_times or []

    options: list[dict] = []
    has_amd = bool(ctx.get("has_amd_chipset") or ctx.get("cpu_vendor") == "amd")
    has_intel = bool(ctx.get("has_intel_chipset") or ctx.get("cpu_vendor") == "intel")
    gpu_vendor = (ctx.get("gpu_vendor") or "").lower()

    def _add_chipset_links() -> None:
        if has_amd:
            options.append({
                "id": "amd_chipset",
                "label": "AMD chipset drivers (for this PC's AMD platform)",
                "reason": report_prefix + (
                    "Chipset/platform driver package from AMD — common fix for WHEA and CPU/platform crashes."
                ) + (" " + bios_note if bios_note else ""),
                "kind": "url",
                "url": _bc("_AMD_CHIPSET_DRIVER_URL"),
            })
        if has_intel:
            options.append({
                "id": "intel_chipset",
                "label": "Intel chipset / INF drivers (for this PC's Intel platform)",
                "reason": report_prefix + (
                    "Intel chipset (INF) drivers — common fix for WHEA and CPU/platform crashes."
                ) + (" " + bios_note if bios_note else ""),
                "kind": "url",
                "url": "https://www.intel.com/content/www/us/en/download/19351/chipset-inf-utility.html",
            })
        elif ff.get("focus") == FIX_UNCERTAIN:
            options.append({
                "id": "amd_chipset_guess",
                "label": "AMD chipset drivers (if this is an AMD PC)",
                "reason": report_prefix + "Use when the processor is AMD.",
                "kind": "url",
                "url": _bc("_AMD_CHIPSET_DRIVER_URL"),
            })
            options.append({
                "id": "intel_chipset_guess",
                "label": "Intel chipset drivers (if this is an Intel PC)",
                "reason": report_prefix + "Use when the processor is Intel.",
                "kind": "url",
                "url": "https://www.intel.com/content/www/us/en/download/19351/chipset-inf-utility.html",
            })

    def _add_gpu_links() -> None:
        if gpu_vendor and gpu_vendor in _bc("_VENDOR_DRIVER_URLS"):
            url, title = _bc("_VENDOR_DRIVER_URLS")[gpu_vendor]
            tag = ""
            if code_val == 0xEA:
                tag = " (display driver stop code)"
            elif p1_int == 0x4:
                tag = " (report points at PCIe/GPU)"
            options.append({
                "id": f"gpu_{gpu_vendor}_report",
                "label": title + tag,
                "reason": report_prefix + (
                    "Included because the crash logs or dump point at graphics/PCIe — "
                    f"not because this PC has a {gpu_vendor} GPU installed."
                ),
                "kind": "url",
                "url": url,
            })

    if ff.get("include_chipset", True) and ff.get("focus") != FIX_GRAPHICS:
        _add_chipset_links()
    if ff.get("include_gpu") or (
        not ff
        and _gpu_relevant_to_crash(
            code_val, p1_int, whea_component, faulting_driver, reliability_ctx, times,
        )
    ):
        _add_gpu_links()
    if ff.get("include_storage") or (
        not ff
        and _pcie_storage_relevant(p1_int, whea_component, faulting_driver)
    ):
        if ctx.get("has_nvme"):
            options.append({
                "id": "storage_nvme_search",
                "label": "Search storage/NVMe driver updates for this PC",
                "reason": report_prefix + "PCIe/storage-related signals in the crash logs.",
                "kind": "url",
                "url": "https://www.google.com/search?q="
                + urllib.parse.quote_plus(
                    f"{ctx.get('system_manufacturer', '')} {ctx.get('system_model', '')} NVMe driver download".strip()
                ),
            })

    if ff.get("include_whea_search", bool(whea_component)) and whea_component:
        options.append({
            "id": "whea_component_search",
            "label": f"Search driver/firmware for: {whea_component[:60]}",
            "reason": report_prefix + "Targeted search using the component named in the WHEA event log.",
            "kind": "url",
            "url": "https://www.google.com/search?q="
            + urllib.parse.quote_plus(f"{whea_component} driver firmware update download"),
        })

    model_url = _bc("_oem_model_support_url")(ctx)
    mfr = (ctx.get("system_manufacturer") or "your PC maker").strip()
    model = (ctx.get("system_model") or "").strip()
    if model_url and ff.get("include_oem", True):
        if _bc("_is_usable_system_model")(model):
            label = f"Download drivers for this PC ({mfr} {model})"
            reason = (
                report_prefix
                + f"Opens your PC maker's driver page for {mfr} {model}."
            )
        else:
            label = f"Open {mfr} support (drivers & BIOS)"
            reason = report_prefix + "Your PC manufacturer's support site."
        options.append({
            "id": "oem_model_support",
            "label": label,
            "reason": reason + (" " + bios_note if bios_note else ""),
            "kind": "url",
            "url": model_url,
        })

    if ff.get("include_bios", code_val in (0x124, 0x7F, 0x9C)):
        bios_label = f"BIOS / UEFI updates for this PC ({mfr}"
        if _bc("_is_usable_system_model")(model):
            bios_label += f" {model}"
        bios_label += ")"
        options.append({
            "id": "bios_model_search",
            "label": bios_label,
            "reason": report_prefix + (
                "BIOS/UEFI updates often fix hardware (WHEA) crashes — use your PC maker's support site."
            ) + (" " + bios_note if bios_note else ""),
            "kind": "url",
            "url": _bc("_pc_support_bios_url")(ctx),
        })

    options.append({
        "id": "wu_optional_platform",
        "label": "Open Windows Update (optional updates)",
        "reason": (
            "Optional driver updates from Microsoft — stable, but try manufacturer and OEM links "
            "above first for the newest chipset/platform drivers."
        ),
        "kind": "uri",
        "uri": "ms-settings:windowsupdate-optionalupdates",
    })

    return [opt for _, opt in _bc("sort_action_plan_update_options")(options)][:9]

def _merge_update_options(primary: list[dict], extra: list[dict]) -> list[dict]:
    seen = {o.get("id") for o in primary if o.get("id")}
    merged = list(primary)
    for opt in extra:
        oid = opt.get("id")
        if oid and oid in seen:
            continue
        if oid:
            seen.add(oid)
        merged.append(opt)
    return [opt for _, opt in _bc("sort_action_plan_update_options")(merged)][:9]
