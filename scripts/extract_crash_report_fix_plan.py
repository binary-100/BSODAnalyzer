"""One-shot: extract fix-plan / action-plan link logic from bsod_crash_report.py."""

from __future__ import annotations

import re
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
SRC = APP / "bsod_crash_report.py"
OUT = APP / "crash_report_fix_plan.py"

# FIX_* constants through _merge_update_options (1-based inclusive)
FUNC_RANGE = (892, 1586)

_BC_CALLS = (
    "_match_event_to_crash",
    "_summarize_livekernel_message",
    "_detected_cpu_platform_label",
    "_is_usable_system_model",
    "_system_ctx_with_service_tag",
    "_installed_bios_summary",
    "_pc_support_drivers_url",
    "_pc_support_bios_url",
    "_bios_support_search_url",
    "_oem_model_support_url",
    "sort_action_plan_update_options",
)

_BC_NAMES = (
    "_PLATFORM_CPU_MODULES",
    "_MISLEADING_FAULT_MODULES",
    "_HARDWARE_LEAN_STOP_CODES",
    "_AMD_CHIPSET_DRIVER_URL",
    "_VENDOR_DRIVER_URLS",
    "_RELIABILITY_NEAR_CRASH_WINDOW_MIN",
)


def _patch_bc_refs(text: str) -> str:
    for name in _BC_CALLS:
        text = re.sub(rf"(?<![.\w]){re.escape(name)}\(", f'_bc("{name}")(', text)
    for name in _BC_NAMES:
        text = re.sub(rf"(?<![.\w]){re.escape(name)}\b", f'_bc("{name}")', text)
    return text


def main() -> None:
    lines = SRC.read_text(encoding="utf-8").splitlines(keepends=True)
    start, end = FUNC_RANGE
    body = _patch_bc_refs("".join(lines[start - 1 : end]))

    header = '''"""Crash fix focus, playbook steps, and platform download links (extracted from bsod_crash_report)."""

from __future__ import annotations

from bsod_minidump import minidump_capture_action_step


def _bc(name: str):
    """Lazy bsod_crash_report lookup — avoids import cycles during module load."""
    import bsod_crash_report as bc

    return getattr(bc, name)


'''

    OUT.write_text(header + body, encoding="utf-8")
    print(f"Wrote {OUT} ({len((header + body).splitlines())} lines approx)")

    del lines[start - 1 : end]
    text = "".join(lines)

    import_block = """from crash_report_fix_plan import (
    FIX_BOOT_RECOVERY,
    FIX_CPU_PLATFORM,
    FIX_DRIVER_IRQL,
    FIX_GRAPHICS,
    FIX_MEMORY,
    FIX_NAMED_DRIVER,
    FIX_STORAGE,
    FIX_THERMAL,
    FIX_UNCERTAIN,
    FIX_WHEA_COMPONENT,
    build_boot_failure_playbook_steps,
    build_crash_fix_plan,
    build_platform_update_options,
    derive_report_fix_focus,
    _describe_action_plan_link_basis,
    _merge_update_options,
    _needs_platform_driver_links,
)

"""
    needle = "from crash_report_culprit import ("
    if needle not in text:
        raise SystemExit("crash_report_culprit import anchor not found")
    idx = text.index(needle)
    end_idx = text.index("\n)\n", idx) + len("\n)\n")
    text = text[:end_idx] + "\n" + import_block + text[end_idx:]

    SRC.write_text(text, encoding="utf-8")
    print(f"Updated {SRC}")


if __name__ == "__main__":
    main()
