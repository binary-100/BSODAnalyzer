"""Workflow gating: crash troubleshooting vs full-install driver checks."""

from __future__ import annotations

INVENTORY_SUMMARY_KEYS = (
    "plain_english",
    "fix_plan",
    "recommendations",
    "culprit_driver_info",
    "culprit_device_names",
    "driver_update_options",
    "action_plan_link_basis",
    "culprit_callout",
    "cause_title",
    "cause_subtitle",
    "crash_repair_narrative",
    "hardware_findings",
)

INVENTORY_CRASH_VIEW_KEYS = (
    "incidents",
    "hardware_findings",
    "log_coverage",
    "culprit_callout",
    "crash_count",
    "confidence",
    "crash_timeline",
    "incident_timeline",
    "culprit_driver_info",
    "culprit_device_names",
    "driver_update_options",
    "data_gaps",
)


def has_crash_analysis_context(model: dict | None, fmt_args: tuple | None) -> bool:
    return bool(model and fmt_args)


def should_refresh_crash_details_after_hardware(
    *,
    full_install: bool,
    model: dict | None,
    fmt_args: tuple | None,
    hardware_ready: bool,
) -> bool:
    """Full install + prior crash analysis + inventory: refresh Crash Details tab."""
    return (
        full_install
        and hardware_ready
        and has_crash_analysis_context(model, fmt_args)
    )


def merge_display_keys(target: dict, source: dict, keys: tuple[str, ...]) -> None:
    for key in keys:
        if key in source:
            target[key] = source[key]


def hardware_profile_for_summary_refresh(prof: dict | None) -> dict | None:
    """Shallow profile for off-thread summary rebuild — avoids deep-copying all_drivers."""
    if not prof:
        return None
    bio = dict(prof.get("bios_driver_info") or {})
    bio.pop("all_drivers", None)
    return {
        "pnp_list": list(prof.get("pnp_list") or []),
        "system_ctx": dict(prof.get("system_ctx") or {}),
        "bios_driver_info": bio,
        "devices_with_generic_driver": list(
            prof.get("devices_with_generic_driver") or []
        ),
        "devices_with_driver_problems": list(
            prof.get("devices_with_driver_problems") or []
        ),
        "ssd_firmware": list(prof.get("ssd_firmware") or []),
    }


def merge_hardware_into_fmt_args(
    fmt_args: tuple,
    prof: dict | None,
) -> tuple:
    """Overlay full hardware-scan inventory onto analysis fmt_args for rebuild."""
    if not prof:
        return fmt_args
    fa = list(fmt_args)
    bio = prof.get("bios_driver_info")
    if bio:
        fa[13] = bio
    sc = dict(fa[14] if len(fa) > 14 else {})
    prof_sc = prof.get("system_ctx") or {}
    for key in (
        "pnp_list", "pnp_enrichment", "monitor_edid",
        "has_nvme", "has_sata", "gpu_vendor", "gpu_vendors_present",
        "hardware_vendors", "has_amd_chipset", "has_intel_chipset", "data_gaps",
    ):
        val = prof_sc.get(key)
        if val:
            sc[key] = val
    present = prof_sc.get("present_drivers")
    if present:
        existing = sc.get("present_drivers") or set()
        if isinstance(existing, set) and isinstance(present, set):
            sc["present_drivers"] = existing | present
        else:
            sc["present_drivers"] = present
    if len(fa) > 14:
        fa[14] = sc
    if prof.get("devices_with_driver_problems") is not None and len(fa) > 15:
        fa[15] = prof.get("devices_with_driver_problems")
    if prof.get("devices_with_generic_driver") is not None and len(fa) > 16:
        fa[16] = prof.get("devices_with_generic_driver")
    return tuple(fa)


def drv_workflow_banner_text(
    *,
    full_install: bool,
    crash_context: bool,
    hardware_ready: bool,
    phase: str = "",
    updates: int = 0,
    checked: int = 0,
    batch_note: str = "",
    crash_driver: str = "",
) -> str:
    if phase == "scanning":
        text = "② Checking driver updates…"
        if batch_note:
            text += f" {batch_note}"
        text += (
            " Watch the progress bar below — large scans run in batches and continue "
            "automatically. Updates use version numbers, trustworthy driver dates, and "
            "Windows Update offers (not catalog dates alone)."
        )
        return text
    if phase == "done":
        text = (
            f"③ Update scan complete — {updates} newer package(s) found"
            f" ({checked} device(s) checked)."
        )
        if crash_driver:
            text += f" Crash module: {crash_driver}."
        return text + " Open Updates available or Needs attention."
    if phase == "need_analysis":
        return "① Run crash analysis on the Summary tab to link devices to your crash."
    if phase == "need_hardware":
        return (
            "Run ① Load devices or ② Search for updates "
            "to load hardware inventory (no crash analysis required)."
        )
    if phase == "hardware_ready":
        if full_install and crash_context:
            return (
                "Needs attention shows crash-linked devices after Run Analysis. "
                "Run ① Load devices for All devices, then ② Search for updates."
            )
        return (
            "Check Include on the devices you want, then ② Search for updates. "
            "Run ① Load devices for the full inventory."
        )
    if phase == "full_install":
        return (
            "Saved device list loaded. Run ① Load devices to refresh inventory. "
            "② Search for updates checks Include devices."
        )
    if (
        not phase
        and full_install
        and hardware_ready
        and not crash_context
    ):
        return drv_workflow_banner_text(
            full_install=True,
            crash_context=False,
            hardware_ready=True,
            phase="full_install",
        )
    if full_install:
        return (
            "① Run Analysis · ② Load devices · "
            "③ Include → Search for updates"
        )
    return (
        "① Run Analysis · ② Load devices (optional) · "
        "③ Include → Search for updates"
    )


def fw_workflow_banner_text(
    *,
    full_install: bool,
    crash_context: bool,
    hardware_ready: bool,
    phase: str = "",
    updates: int = 0,
) -> str:
    if phase == "scanning":
        return "② Checking BIOS and SSD firmware sources…"
    if phase == "failed":
        return "③ Firmware scan failed — see status bar and Firmware tab for details."
    if phase == "done":
        return (
            f"③ Firmware scan complete — {updates} component(s) with a newer package."
        )
    if phase == "full_install" or (
        full_install
        and hardware_ready
        and not crash_context
    ):
        return (
            "BIOS row is always shown. Run ① Load components for SSD drives, "
            "then check Include and ② Search for updates."
        )
    if full_install and crash_context and hardware_ready:
        return (
            "Needs attention highlights crash-related firmware after Run Analysis. "
            "Run ① Load components, then Include → ② Search for updates."
        )
    return (
        "① Run Analysis · ② Load components · "
        "③ Include → Search for updates"
    )


def drv_manual_queue_block_reason() -> str | None:
    """Queued manual searches wait on generic_driver_busy when a catalog thread runs."""
    return None


def drv_manual_queue_status_text(
    *,
    queued_devices: int,
    queued_jobs: int,
    block_reason: str | None,
    generic_driver_busy: bool = False,
) -> str:
    """Status bar / Drivers hint when manual searches are queued."""
    if queued_devices <= 0:
        return ""
    if block_reason:
        line = (
            f"Your driver search ({queued_devices} device(s) queued) will run after "
            f"{block_reason}."
        )
    elif generic_driver_busy:
        line = (
            f"Your driver search ({queued_devices} device(s) queued) will run when "
            f"the current catalog check finishes."
        )
    else:
        line = f"Queued: {queued_devices} device(s) — starting shortly."
    if queued_jobs > 1:
        line += f" ({queued_jobs} searches in queue.)"
    return line
