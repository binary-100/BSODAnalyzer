"""One-shot: move CDB + minidump I/O from bsod_analyzer.py to bsod_minidump.py."""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "bsod_analyzer.py"
MINIDUMP = ROOT / "bsod_minidump.py"

NAMES = {
    "minidump_capture_action_step",
    "_file_version",
    "_get_tool_dir",
    "_cdb_arch_dir",
    "_cdb_search_arch_dirs",
    "_get_local_cdb_path",
    "_get_bundled_cdb_path",
    "_find_windbg_app_engine_dir",
    "_get_windbg_app_cdb_path",
    "_cdb_engine_usable",
    "_get_cdb_search_paths",
    "_get_bundled_installer_dir",
    "_find_bundled_installer",
    "_run_bundled_installer",
    "_winget_available_version",
    "install_cdb",
    "get_cdb_version",
    "cdb_status",
    "update_cdb",
    "prompt_install_cdb",
    "clear_cdb_path_cache",
    "find_cdb",
    "scan_for_cdb_and_report",
    "_is_online",
    "_copy_engine_dir",
    "_copy_debuggers_to_local",
    "repair_local_cdb_engine_if_needed",
    "_check_and_offer_cdb_update",
    "find_windbgx",
    "launch_latest_dump_in_windbg",
    "analyze_minidump_with_cdb",
    "_normalize_stack_frame",
    "_kernel_only_stack_top",
    "enrich_windbg_analysis",
    "_expand_windows_path",
    "get_crash_dump_settings",
    "get_minidump_search_directories",
    "get_drive_free_space_mb",
    "minidump_prerequisite_action_steps",
    "assess_minidump_prerequisites",
    "collect_kernel_minidumps",
    "_dump_entry_from_path",
    "parse_report_wer",
    "_module_from_wer_bucket",
    "_wer_report_module_hint",
    "find_wer_archive_report_for_dump",
    "_search_minidump_by_basename",
    "reconcile_wer_dumpfile_gaps",
    "merge_recovered_kernel_dumps",
    "build_capture_readiness",
    "list_dumps",
    "list_dumps_from_paths",
    "check_full_dump",
    "get_dump_config",
    "configure_memory_dump",
    "enable_memory_dumps_or_report_status",
}

ASSIGN_NAMES = {
    "CRASH_CONTROL_KEY",
    "DUMP_TYPES",
    "WINDOWS_DIR",
    "MINIDUMP_DIR",
    "FULL_DUMP_PATH",
    "MINIDUMP_DISK_WARN_MB",
    "MINIDUMP_DISK_CRITICAL_MB",
    "WER_REPORT_ARCHIVE",
    "WINDBGX_PATHS",
    "WINDBG_WINGET_PACKAGE",
    "BUNDLED_INSTALLER_SUBDIR",
    "WINSDK_SETUP_NAME",
    "WINSDK_SILENT_ARGS",
    "CDB_INSTALL_EXPLANATION",
    "_KERNEL_MODULE_ALIASES",
    "_DUMP_EVENT_MATCH_HOURS",
    "_CDB_CACHE_UNSET",
    "_CDB_PATH_CACHE",
    "_CDB_COPY_SKIP_DIRS",
}

CLASS_NAMES = {"_VS_FIXEDFILEINFO"}

_LAZY_BA_FUNCS = (
    "is_user_admin",
    "_parse_event_time",
    "_dump_matches_recent_events",
)

MODULE_HEADER = '''"""CDB debugger tooling and minidump discovery / WER recovery."""
from __future__ import annotations

import ctypes
import glob
import os
import platform
import re
import shutil
import socket
import subprocess
import sys
import time
from datetime import datetime

import log_read_windows as lrw

from bsod_runtime import console_print


def _ba(name: str):
    """Lazy bsod_analyzer lookup — avoids import cycles during module load."""
    import bsod_analyzer as ba

    return getattr(ba, name)


'''

RE_EXPORTS = """from bsod_minidump import (
    CRASH_CONTROL_KEY,
    DUMP_TYPES,
    FULL_DUMP_PATH,
    MINIDUMP_DIR,
    MINIDUMP_DISK_CRITICAL_MB,
    MINIDUMP_DISK_WARN_MB,
    WER_REPORT_ARCHIVE,
    WINDOWS_DIR,
    analyze_minidump_with_cdb,
    assess_minidump_prerequisites,
    build_capture_readiness,
    cdb_status,
    check_full_dump,
    clear_cdb_path_cache,
    collect_kernel_minidumps,
    configure_memory_dump,
    enable_memory_dumps_or_report_status,
    enrich_windbg_analysis,
    find_cdb,
    find_windbgx,
    get_crash_dump_settings,
    get_cdb_version,
    get_dump_config,
    get_drive_free_space_mb,
    get_minidump_search_directories,
    install_cdb,
    launch_latest_dump_in_windbg,
    list_dumps,
    list_dumps_from_paths,
    merge_recovered_kernel_dumps,
    minidump_capture_action_step,
    minidump_prerequisite_action_steps,
    parse_report_wer,
    prompt_install_cdb,
    reconcile_wer_dumpfile_gaps,
    repair_local_cdb_engine_if_needed,
    scan_for_cdb_and_report,
    update_cdb,
    update_cdb,
    _cdb_engine_usable,
    _cdb_search_arch_dirs,
    _DUMP_EVENT_MATCH_HOURS,
    _expand_windows_path,
    _get_local_cdb_path,
    _module_from_wer_bucket,
    _wer_report_module_hint,
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


def main() -> int:
    src = CORE.read_text(encoding="utf-8")
    tree = ast.parse(src)
    lines = src.splitlines(keepends=True)

    extracted: list[tuple[int, str]] = []
    remove_ranges: list[tuple[int, int]] = []

    for node in tree.body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            if node.name not in NAMES:
                continue
            start = node.lineno - 1
            end = node.end_lineno or node.lineno
            chunk = _patch_lazy_refs("".join(lines[start:end]))
            extracted.append((start, chunk))
            remove_ranges.append((start, end))
        elif isinstance(node, ast.ClassDef):
            if node.name not in CLASS_NAMES:
                continue
            start = node.lineno - 1
            end = node.end_lineno or node.lineno
            extracted.append((start, "".join(lines[start:end]) + "\n"))
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
        if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef) and n.name in NAMES
    }
    missing = NAMES - found_funcs
    if missing:
        print(f"Missing defs: {sorted(missing)}", file=sys.stderr)
        return 1

    if MINIDUMP.is_file() and "def find_cdb(" in MINIDUMP.read_text(encoding="utf-8"):
        print("Already extracted — skip", file=sys.stderr)
        return 0

    extracted.sort(key=lambda x: x[0])
    body = "\n\n".join(c.rstrip() for _, c in extracted) + "\n"
    MINIDUMP.write_text(MODULE_HEADER + body, encoding="utf-8")

    new_lines = list(lines)
    for start, end in sorted(remove_ranges, reverse=True):
        del new_lines[start:end]
    CORE.write_text("".join(new_lines), encoding="utf-8")

    core = CORE.read_text(encoding="utf-8")
    if "from bsod_minidump import (" not in core:
        anchor = "from bsod_hardware_wmi import ("
        idx = core.find(anchor)
        if idx == -1:
            print("Could not find insert point for minidump imports", file=sys.stderr)
            return 1
        # Insert after the second bsod_hardware_wmi import block (after line with _parse_json_date)
        second = core.find(anchor, idx + 1)
        end_block = core.find(")\n", second if second != -1 else idx)
        if end_block == -1:
            print("Could not find end of hardware_wmi imports", file=sys.stderr)
            return 1
        insert_at = end_block + 2
        core = core[:insert_at] + "\n" + RE_EXPORTS + core[insert_at:]
        CORE.write_text(core, encoding="utf-8")

    print(f"Extracted {len(extracted)} blocks into bsod_minidump.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
