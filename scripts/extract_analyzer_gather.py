"""One-shot: extract gather_report_data from bsod_analyzer.py."""

from __future__ import annotations

import re
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
SRC = APP / "bsod_analyzer.py"
OUT = APP / "analyzer_gather.py"

FUNC_RANGE = (246, 648)

# After gather extract, re-measure hardware range before extract_analyzer_hardware.py.

_PATCHABLE = frozenset({
    "query_bugcheck_events", "query_boot_recovery_events", "collect_kernel_minidumps",
    "check_full_dump", "list_dumps_from_paths", "query_application_crashes",
    "get_bios_and_driver_versions", "find_cdb", "get_crash_dump_settings",
    "query_whea_hardware_errors", "query_thermal_events", "get_pnp_entities_for_analysis",
    "get_all_installed_driver_devices", "query_reliability_livekernel_bundle",
    "get_logged_in_user_paths", "get_report_storage_wmi_bundle", "get_storage_and_system_context",
    "get_wmi_monitor_edid_by_device_id", "build_hardware_enrichment_bundle",
    "enrich_bios_driver_info", "device_inventory_for_matching",
    "get_devices_with_driver_problems", "get_devices_with_generic_driver",
    "get_ssd_firmware_inventory", "assess_minidump_prerequisites", "reconcile_wer_dumpfile_gaps",
    "merge_recovered_kernel_dumps", "repair_local_cdb_engine_if_needed", "clear_cdb_path_cache",
    "analyze_recent_minidumps", "_get_local_cdb_path", "_cdb_engine_usable",
    "_analysis_gap_message", "minidump_without_bugcheck_gap",
})


def _patch_line(line: str) -> str:
    if line.lstrip().startswith("def "):
        return line
    for name in sorted(_PATCHABLE, key=len, reverse=True):
        line = re.sub(rf"\b{re.escape(name)}\(", f'_ba("{name}")(', line)
    return line


def main() -> None:
    lines = SRC.read_text(encoding="utf-8").splitlines(keepends=True)
    start, end = FUNC_RANGE
    body = "".join(_patch_line(l) for l in lines[start - 1 : end])

    header = '''"""Run Analysis data gathering (extracted from bsod_analyzer)."""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable


def _ba(name: str):
    """Lazy bsod_analyzer lookup — keeps mock.patch('bsod_analyzer.*') working in tests."""
    import bsod_analyzer as ba

    return getattr(ba, name)


'''

    if OUT.exists():
        raise SystemExit(f"{OUT.name} already exists — remove or rename before re-running.")

    if "def gather_report_data" not in SRC.read_text(encoding="utf-8"):
        raise SystemExit(f"{SRC.name} has no gather_report_data — already extracted?")

    OUT.write_text(header + body, encoding="utf-8")
    print(f"Wrote {OUT} ({len((header + body).splitlines())} lines approx)")

    del lines[start - 1 : end]
    text = "".join(lines)

    import_block = """from analyzer_gather import gather_firmware_inventory_for_gui, gather_report_data

"""
    needle = "from bsod_crash_report import ("
    if needle not in text:
        raise SystemExit("bsod_crash_report import anchor not found")
    idx = text.index(needle)
    end_idx = text.index("\n)\n", idx) + len("\n)\n")
    text = text[:end_idx] + "\n" + import_block + text[end_idx:]

    SRC.write_text(text, encoding="utf-8")
    print(f"Updated {SRC}")


if __name__ == "__main__":
    main()
