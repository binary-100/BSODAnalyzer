"""One-shot: extract narrative / log-summary helpers from bsod_crash_report.py."""

from __future__ import annotations

import re
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
SRC = APP / "bsod_crash_report.py"
OUT = APP / "crash_report_narrative.py"

# 1-based inclusive ranges (cause typing + log narrative helpers)
RANGES = ((370, 488), (1288, 1783))

_BC_CALLS = (
    "get_faulting_device_explanation",
    "_detected_cpu_platform_label",
)

_BC_NAMES = (
    "GENERIC_FAULT_MODULE_DEVICE",
    "_PLATFORM_CPU_MODULES",
    "_KERNEL_SHIM_MODULES",
    "_HARDWARE_LEAN_STOP_CODES",
    "_MISLEADING_FAULT_MODULES",
    "_WHEA_NEAR_CRASH_WINDOW_MIN",
    "_THERMAL_NEAR_CRASH_WINDOW_MIN",
    "_RELIABILITY_NEAR_CRASH_WINDOW_MIN",
    "_INCIDENT_WHEA_WINDOW_MIN",
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
    chunks: list[str] = []
    remove: list[tuple[int, int]] = []
    for start, end in RANGES:
        chunks.append(_patch_bc_refs("".join(lines[start - 1 : end])))
        remove.append((start - 1, end))

    header = '''"""Cause typing and log narrative helpers (extracted from bsod_crash_report)."""

from __future__ import annotations

from datetime import datetime

import log_read_windows as lrw

from crash_report_culprit import DRIVER_TO_HARDWARE, _infer_driver_vendor
from crash_report_fix_plan import _GPU_DRIVER_FRAGMENTS
from crash_report_timeline import _dump_matches_event_time


def _bc(name: str):
    """Lazy bsod_crash_report lookup — avoids import cycles during module load."""
    import bsod_crash_report as bc

    return getattr(bc, name)


'''

    body = "\n\n".join(c.rstrip() for c in chunks) + "\n"
    OUT.write_text(header + body, encoding="utf-8")
    print(f"Wrote {OUT} ({len((header + body).splitlines())} lines approx)")

    for start, end in sorted(remove, reverse=True):
        del lines[start:end]
    text = "".join(lines)

    import_block = """from crash_report_narrative import (
    boot_events_near_crash,
    build_crash_confidence_summary,
    build_event_log_coverage_summary,
    build_hardware_findings_from_logs,
    infer_likely_cause_type,
    _analysis_confidence_label,
    _build_definitive_cause,
    _build_plain_english_summary,
    _match_event_to_crash,
    _plain_english_from_repair_narrative,
    _reliability_events_near_crash,
    _summarize_livekernel_message,
    _user_friendly_stop_summary,
)

"""
    needle = "from crash_report_format import ("
    if needle not in text:
        raise SystemExit("crash_report_format import anchor not found")
    idx = text.index(needle)
    end_idx = text.index("\n)\n", idx) + len("\n)\n")
    text = text[:end_idx] + "\n" + import_block + text[end_idx:]

    SRC.write_text(text, encoding="utf-8")
    print(f"Updated {SRC}")


if __name__ == "__main__":
    main()
