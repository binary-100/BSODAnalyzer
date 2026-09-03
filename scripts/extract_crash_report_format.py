"""One-shot: extract text/GUI report formatting from bsod_crash_report.py."""

from __future__ import annotations

import re
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
SRC = APP / "bsod_crash_report.py"
OUT = APP / "crash_report_format.py"

# _REPORT_WIDTH through build_display_model (1-based inclusive)
FUNC_RANGE = (1762, 3268)

_BC_CALLS = (
    "infer_likely_cause_type",
    "get_bugcheck_info",
    "_analysis_confidence_label",
    "_crash_report_context",
    "build_hardware_findings_from_logs",
    "build_event_log_coverage_summary",
    "_plain_english_from_repair_narrative",
    "_build_plain_english_summary",
    "build_crash_confidence_summary",
    "merge_verification_action_steps",
    "build_driver_update_options",
    "get_culprit_device_driver_info",
    "get_faulting_device_explanation",
    "_build_definitive_cause",
    "_user_friendly_stop_summary",
    "_match_event_to_crash",
    "boot_events_near_crash",
    "_system_ctx_with_service_tag",
    "resolve_device_display_label",
    "_installed_bios_summary",
    "_pc_support_drivers_url",
    "run_driver_update_option",
    "newest_minidump_analysis",
    "analyze_recent_minidumps",
)

_BC_NAMES = (
    "_INCIDENT_WHEA_WINDOW_MIN",
    "_RELIABILITY_NEAR_CRASH_WINDOW_MIN",
    "_WHEA_NEAR_CRASH_WINDOW_MIN",
    "_THERMAL_NEAR_CRASH_WINDOW_MIN",
    "BUGCHECK_CODES",
    "GENERIC_FAULT_MODULE_DEVICE",
    "WHEA_P1_SOURCE",
)


def _patch_bc_refs(text: str) -> str:
    out_lines: list[str] = []
    for line in text.splitlines(keepends=True):
        stripped = line.lstrip()
        if stripped.startswith("def ") or stripped.startswith("async def "):
            out_lines.append(line)
            continue
        patched = line
        for name in _BC_CALLS:
            patched = re.sub(rf"(?<![.\w]){re.escape(name)}\(", f'_bc("{name}")(', patched)
        for name in _BC_NAMES:
            patched = re.sub(rf"(?<![.\w]){re.escape(name)}\b", f'_bc("{name}")', patched)
        out_lines.append(patched)
    return "".join(out_lines)


def main() -> None:
    lines = SRC.read_text(encoding="utf-8").splitlines(keepends=True)
    start, end = FUNC_RANGE
    body = _patch_bc_refs("".join(lines[start - 1 : end]))

    header = '''"""Text report formatting and GUI display model (extracted from bsod_crash_report)."""

from __future__ import annotations

from datetime import datetime

import log_read_windows as lrw

from bsod_minidump import assess_minidump_prerequisites, build_capture_readiness
from crash_report_culprit import (
    build_culprit_system_callout,
    find_culprit_devices,
    has_crash_faulting_driver,
    lookup_inventory_row,
    resolve_crash_culprit_context,
    _filter_possible_drivers_list,
)
from crash_report_events import group_events_by_incident as _group_events_by_incident
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


'''

    OUT.write_text(header + body, encoding="utf-8")
    print(f"Wrote {OUT} ({len((header + body).splitlines())} lines approx)")

    del lines[start - 1 : end]
    text = "".join(lines)

    import_block = """from crash_report_format import (
    _ANALYSIS_TASK_LABELS,
    _MAX_LINE_LEN,
    _REPORT_WIDTH,
    _analysis_gap_message,
    _build_recommendations,
    _build_summary,
    _friendly_driver_label,
    _quick_answer_lines,
    _section_header,
    _severity_for_display,
    _wrap_text,
    _wrap_with_prefix,
    build_display_model,
    build_report_derivations,
    format_output,
    format_output_from_fmt_args,
    minidump_without_bugcheck_gap,
)

"""
    needle = "from crash_report_fix_plan import ("
    if needle not in text:
        raise SystemExit("crash_report_fix_plan import anchor not found")
    idx = text.index(needle)
    end_idx = text.index("\n)\n", idx) + len("\n)\n")
    text = text[:end_idx] + "\n" + import_block + text[end_idx:]

    SRC.write_text(text, encoding="utf-8")
    print(f"Updated {SRC}")


if __name__ == "__main__":
    main()
