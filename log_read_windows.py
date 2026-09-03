"""Phase 3 — log read windows and primary-incident relevance (single source of truth).

Documented in KNOWN_LIMITATIONS.md § Log read windows.
"""

from __future__ import annotations

from datetime import datetime, timedelta

# Calendar window: incidents older than this before the latest incident are "historical".
PRIMARY_INCIDENT_DAYS = 30

# Minidump time match for latest-incident attribution (see bsod_analyzer._DUMP_EVENT_MATCH_HOURS).
DUMP_INCIDENT_MATCH_HOURS = 72

# --- Event log fetch limits (newest N records per source; not calendar cutoffs) ---
CRASH_WER1001_MAX = 30
CRASH_KERNEL_POWER_41_MAX = 20
CRASH_UNEXPECTED_SHUTDOWN_6008_MAX = 15
CRASH_EVENTS_RETURN_CAP = 25

BOOT_STARTUP_REPAIR_MAX = 20
BOOT_KERNEL_BOOT_MAX = 30
BOOT_WININIT_MAX = 25

WHEA_LOGGER_MAX = 15
THERMAL_EVENTS_MAX = 20
APP_CRASH_EVENTS_MAX = 30

RELIABILITY_LIVEKERNEL_MAX = 25
RELIABILITY_WER_SYSTEM_MAX = 20

MINIDUMP_ANALYZE_MAX = 3
INCIDENT_TIMELINE_ENTRIES_MAX = 12
INCIDENT_GROUP_WINDOW_MINUTES = 2


def parse_log_timestamp(time_str: str) -> datetime | None:
    if not time_str or time_str == "?":
        return None
    try:
        return datetime.strptime(time_str.strip()[:19], "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def is_outside_primary_window(
    event_time: str,
    anchor_time: str,
    *,
    primary_days: int = PRIMARY_INCIDENT_DAYS,
) -> bool:
    """True when event_time is more than primary_days before anchor_time (latest incident)."""
    evt_dt = parse_log_timestamp(event_time)
    anchor_dt = parse_log_timestamp(anchor_time)
    if not evt_dt or not anchor_dt:
        return False
    return anchor_dt - evt_dt > timedelta(days=primary_days)


def read_windows_as_dict() -> dict:
    """Machine-readable read windows for tests and export."""
    return {
        "primary_incident_days": PRIMARY_INCIDENT_DAYS,
        "dump_incident_match_hours": DUMP_INCIDENT_MATCH_HOURS,
        "crash_events": {
            "wer1001_max": CRASH_WER1001_MAX,
            "kernel_power_41_max": CRASH_KERNEL_POWER_41_MAX,
            "unexpected_shutdown_6008_max": CRASH_UNEXPECTED_SHUTDOWN_6008_MAX,
            "merged_return_cap": CRASH_EVENTS_RETURN_CAP,
        },
        "boot_recovery": {
            "startup_repair_max": BOOT_STARTUP_REPAIR_MAX,
            "kernel_boot_max": BOOT_KERNEL_BOOT_MAX,
            "wininit_max": BOOT_WININIT_MAX,
        },
        "hardware_and_apps": {
            "whea_logger_max": WHEA_LOGGER_MAX,
            "thermal_max": THERMAL_EVENTS_MAX,
            "application_crash_max": APP_CRASH_EVENTS_MAX,
        },
        "reliability": {
            "livekernel_max": RELIABILITY_LIVEKERNEL_MAX,
            "wer_system_max": RELIABILITY_WER_SYSTEM_MAX,
        },
        "minidumps": {
            "analyze_max": MINIDUMP_ANALYZE_MAX,
            "note": "All .dmp files under registry/default MinidumpDir are listed; oldest may predate event log window.",
        },
    }


def read_windows_detail_lines() -> list[str]:
    """Human-readable lines for export and KNOWN_LIMITATIONS."""
    w = read_windows_as_dict()
    ce = w["crash_events"]
    br = w["boot_recovery"]
    ha = w["hardware_and_apps"]
    rel = w["reliability"]
    md = w["minidumps"]
    return [
        f"Primary incident window: {w['primary_incident_days']} days before the latest incident "
        "(older rows labeled Historical in timeline/export).",
        f"Minidump↔incident time match: {w['dump_incident_match_hours']} hours.",
        "System crash events (newest records per source): "
        f"WER BugCheck 1001 ×{ce['wer1001_max']}, "
        f"Kernel-Power 41 ×{ce['kernel_power_41_max']}, "
        f"unexpected shutdown 6008 ×{ce['unexpected_shutdown_6008_max']} "
        f"(merged cap {ce['merged_return_cap']}).",
        "Boot/recovery: "
        f"Startup Repair ×{br['startup_repair_max']}, "
        f"Kernel-Boot ×{br['kernel_boot_max']}, "
        f"Wininit (filtered) ×{br['wininit_max']}.",
        "Hardware/apps: "
        f"WHEA-Logger 18 ×{ha['whea_logger_max']}, "
        f"thermal ×{ha['thermal_max']}, "
        f"Application Error 1000 ×{ha['application_crash_max']}.",
        "Reliability (optional setting): "
        f"Live Kernel ×{rel['livekernel_max']}, "
        f"WER system ×{rel['wer_system_max']}.",
        f"Minidumps: list all on disk; analyze up to {md['analyze_max']} newest with WinDbg/CDB.",
    ]


def build_stale_dump_note(
    windbg_analysis: dict | None,
    *,
    latest_incident_date: str = "",
) -> str:
    """3c — explicit separation when dump analysis exists but not for the latest incident."""
    if not windbg_analysis:
        return ""
    dump_t = (windbg_analysis.get("dump_time") or "").strip()
    if not dump_t:
        return ""
    dump_f = (windbg_analysis.get("dump_file") or "").strip()
    drv = (windbg_analysis.get("faulting_driver") or "").strip()
    ktop = (windbg_analysis.get("kernel_stack_top") or "").strip()
    bc = windbg_analysis.get("bugcheck_code")
    hint = drv or ktop
    if not hint and bc not in (None, "", "?"):
        hint = f"bugcheck {bc}"
    if not hint:
        return ""
    date_bit = dump_t[:10] if dump_t else dump_t
    file_bit = f" ({dump_f})" if dump_f else ""
    latest_bit = ""
    if latest_incident_date and date_bit and latest_incident_date[:10] != date_bit[:10]:
        latest_bit = f" The latest incident is {latest_incident_date[:10]}."
    return (
        f"Separate note: an older minidump from {date_bit}{file_bit} mentioned {hint}. "
        f"That is a different incident — it does not explain the latest shutdown.{latest_bit}"
    )
