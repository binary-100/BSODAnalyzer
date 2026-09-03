"""One-shot: move crash analysis + report formatting from bsod_analyzer.py to bsod_crash_report.py."""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "bsod_analyzer.py"
REPORT = ROOT / "bsod_crash_report.py"

SKIP_FUNCS = frozenset({
    "gather_firmware_inventory_for_gui",
    "gather_report_data",
    "_gather_hardware_profile_legacy",
    "gather_hardware_profile",
    "run_analysis",
    "main",
    "probe_cdb_path",
    "probe_mscatalog_module",
    "launch_gui",
    "request_admin_elevation",
    "is_user_admin",
})

EXTRA_FUNCS = frozenset({
    "_friendly_driver_label",
    "_severity_for_display",
    "build_report_derivations",
    "format_output_from_fmt_args",
    "build_display_model",
})

ASSIGN_NAMES = frozenset({
    "_WHEA_NEAR_CRASH_WINDOW_MIN",
    "_THERMAL_NEAR_CRASH_WINDOW_MIN",
    "_RELIABILITY_NEAR_CRASH_WINDOW_MIN",
    "_INCIDENT_WHEA_WINDOW_MIN",
    "BUGCHECK_CODES",
    "WHEA_P1_SOURCE",
    "GENERIC_FAULT_MODULE_DEVICE",
    "POSSIBLE_DRIVERS",
    "DRIVER_VENDOR_PREFIX",
    "DRIVER_TO_HARDWARE",
    "CRASH_SYNTH_DEVICE_PREFIX",
    "FIX_BOOT_RECOVERY",
    "FIX_CPU_PLATFORM",
    "FIX_DRIVER_IRQL",
    "FIX_GRAPHICS",
    "FIX_MEMORY",
    "FIX_NAMED_DRIVER",
    "FIX_STORAGE",
    "FIX_THERMAL",
    "FIX_UNCERTAIN",
    "FIX_WHEA_COMPONENT",
    "_HW_CATEGORY_TO_CLASSES",
    "_AMD_GPU_DRIVER_FRAGMENTS",
    "_AMD_CHIPSET_DRIVER_FRAGMENTS",
    "_VENDOR_IN_NAME_RE",
    "_AMD_CHIPSET_DEVICE_RE",
    "_INTEL_CHIPSET_DRIVER_FRAGMENTS",
    "_STORAGE_FAULT_MODULES",
    "_NETWORK_FAULT_MODULES",
    "_VIRTUAL_NET_DEVICE_RE",
    "_GRAPHICS_FAULT_MODULES",
    "_DRIVER_CLASS_HINTS",
    "_PLATFORM_CPU_MODULES",
    "_MISLEADING_FAULT_MODULES",
    "_KERNEL_SHIM_MODULES",
    "_HARDWARE_LEAN_STOP_CODES",
    "_OEM_SUPPORT_URLS",
    "_VENDOR_DRIVER_URLS",
    "_AMD_CHIPSET_DRIVER_URL",
    "_EDID_MONITOR_MANUFACTURER",
    "_GPU_DRIVER_FRAGMENTS",
    "_REPORT_WIDTH",
    "_MAX_LINE_LEN",
    "_ANALYSIS_TASK_LABELS",
})

_LAZY_BA_FUNCS = ("is_user_admin",)

MODULE_HEADER = '''"""Crash analysis, recommendations, and text/GUI report formatting."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from typing import Callable

import device_enrichment as de
import log_read_windows as lrw

from bsod_events import compute_crash_timeline
from bsod_hardware_wmi import (
    CHIPSET_DEVICE_AMD,
    CHIPSET_DEVICE_INTEL,
    _extract_vendor_from_string,
    _parse_json_date,
)
from bsod_minidump import (
    _DUMP_EVENT_MATCH_HOURS,
    analyze_minidump_with_cdb,
    minidump_capture_action_step,
)
from bsod_runtime import run_powershell


def _ba(name: str):
    """Lazy bsod_analyzer lookup — avoids import cycles during module load."""
    import bsod_analyzer as ba

    return getattr(ba, name)


'''

RE_EXPORTS = """from bsod_crash_report import (
    BUGCHECK_CODES,
    DRIVER_TO_HARDWARE,
    DRIVER_VENDOR_PREFIX,
    GENERIC_FAULT_MODULE_DEVICE,
    POSSIBLE_DRIVERS,
    WHEA_P1_SOURCE,
    analyze_recent_minidumps,
    boot_events_near_crash,
    build_boot_failure_playbook_steps,
    build_crash_confidence_summary,
    build_crash_fix_plan,
    build_culprit_system_callout,
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
    format_output,
    format_output_from_fmt_args,
    get_bugcheck_info,
    get_culprit_device_driver_info,
    get_faulting_device_explanation,
    get_wmi_monitor_edid_by_device_id,
    has_crash_faulting_driver,
    infer_likely_cause_type,
    is_crash_synthetic_device_key,
    is_platform_chipset_device_key,
    lookup_inventory_row,
    merge_verification_action_steps,
    minidump_without_bugcheck_gap,
    platform_chipset_crash_attention,
    refresh_model_culprit_fields,
    resolve_crash_code,
    resolve_crash_culprit_context,
    resolve_device_display_label,
    run_driver_update_option,
    sort_action_plan_update_options,
    _analysis_gap_message,
    _dump_matches_recent_events,
    _find_pnp_entity_by_device_name,
    _infer_driver_vendor,
    _OEM_SUPPORT_URLS,
    _system_manufacturer_oem_url,
    _VENDOR_DRIVER_URLS,
)
"""


def _patch_lazy_refs(source: str) -> str:
    for name in _LAZY_BA_FUNCS:
        source = source.replace(f"{name}(", f"_ba('{name}')(")
    return source


def _assign_target_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    return None


def _collect_names(tree: ast.Module) -> tuple[set[str], set[str]]:
    funcs: set[str] = set()
    assigns: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            if node.name in SKIP_FUNCS:
                continue
            if node.name in EXTRA_FUNCS or (483 <= node.lineno < 5068):
                funcs.add(node.name)
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                name = _assign_target_name(t)
                if name and name in ASSIGN_NAMES:
                    assigns.add(name)
        elif isinstance(node, ast.AnnAssign):
            name = _assign_target_name(node.target)
            if name and name in ASSIGN_NAMES:
                assigns.add(name)
    return funcs, assigns


def main() -> int:
    src = CORE.read_text(encoding="utf-8")
    tree = ast.parse(src)
    lines = src.splitlines(keepends=True)
    names, expected_assigns = _collect_names(tree)

    extracted: list[tuple[int, str]] = []
    remove_ranges: list[tuple[int, int]] = []

    for node in tree.body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            if node.name not in names:
                continue
            start = node.lineno - 1
            end = node.end_lineno or node.lineno
            chunk = _patch_lazy_refs("".join(lines[start:end]))
            extracted.append((start, chunk))
            remove_ranges.append((start, end))
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                name = _assign_target_name(t)
                if name and name in ASSIGN_NAMES:
                    start = node.lineno - 1
                    end = node.end_lineno or node.lineno
                    extracted.append((start, "".join(lines[start:end]) + "\n"))
                    remove_ranges.append((start, end))
                    break
        elif isinstance(node, ast.AnnAssign):
            name = _assign_target_name(node.target)
            if name and name in ASSIGN_NAMES:
                start = node.lineno - 1
                end = node.end_lineno or node.lineno
                extracted.append((start, "".join(lines[start:end]) + "\n"))
                remove_ranges.append((start, end))

    found_funcs = {
        n.name
        for n in tree.body
        if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef) and n.name in names
    }
    missing = names - found_funcs
    if missing:
        print(f"Missing defs: {sorted(missing)}", file=sys.stderr)
        return 1

    if REPORT.is_file() and "def format_output(" in REPORT.read_text(encoding="utf-8"):
        print("Already extracted — skip", file=sys.stderr)
        return 0

    extracted.sort(key=lambda x: x[0])
    body = "\n\n".join(c.rstrip() for _, c in extracted) + "\n"
    REPORT.write_text(MODULE_HEADER + body, encoding="utf-8")

    new_lines = list(lines)
    for start, end in sorted(remove_ranges, reverse=True):
        del new_lines[start:end]
    CORE.write_text("".join(new_lines), encoding="utf-8")

    core = CORE.read_text(encoding="utf-8")
    if "from bsod_crash_report import (" not in core:
        anchor = "from bsod_minidump import ("
        idx = core.find(anchor)
        if idx == -1:
            print("Could not find insert point for crash_report imports", file=sys.stderr)
            return 1
        end_block = core.find(")\n", idx)
        if end_block == -1:
            print("Could not find end of minidump imports", file=sys.stderr)
            return 1
        insert_at = end_block + 2
        core = core[:insert_at] + "\n" + RE_EXPORTS + core[insert_at:]
        CORE.write_text(core, encoding="utf-8")

    print(f"Extracted {len(extracted)} blocks into bsod_crash_report.py ({len(names)} functions)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
