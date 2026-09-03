"""One-shot: extract culprit device matching from bsod_crash_report.py."""

from __future__ import annotations

import re
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
SRC = APP / "bsod_crash_report.py"
OUT = APP / "crash_report_culprit.py"

# 1-based inclusive: POSSIBLE_DRIVERS through build_culprit_system_callout
FUNC_RANGE = (224, 987)

_BC_CALLS = (
    "get_faulting_device_explanation",
    "get_culprit_device_driver_info",
    "build_driver_update_options",
)

_BC_NAMES = (
    "FIX_CPU_PLATFORM",
    "FIX_WHEA_COMPONENT",
    "FIX_UNCERTAIN",
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

    header = '''"""Culprit device matching and crash attribution context (extracted from bsod_crash_report)."""

from __future__ import annotations

import re

from bsod_hardware_wmi import (
    CHIPSET_DEVICE_AMD,
    CHIPSET_DEVICE_INTEL,
    _extract_vendor_from_string,
    chipset_driver_catalog_entries,
)


def _bc(name: str):
    """Lazy bsod_crash_report lookup — avoids import cycles during module load."""
    import bsod_crash_report as bc

    return getattr(bc, name)


_PLATFORM_CPU_MODULES = frozenset({"authenticamd", "genuineintel", "centaurhauls"})


'''

    OUT.write_text(header + body, encoding="utf-8")
    print(f"Wrote {OUT} ({len((header + body).splitlines())} lines approx)")

    del lines[start - 1 : end]
    text = "".join(lines)

    import_block = """from crash_report_culprit import (
    CRASH_SYNTH_DEVICE_PREFIX,
    DRIVER_TO_HARDWARE,
    DRIVER_VENDOR_PREFIX,
    POSSIBLE_DRIVERS,
    build_culprit_system_callout,
    crash_synthetic_device_key,
    device_inventory_for_matching,
    find_culprit_devices,
    has_crash_faulting_driver,
    is_crash_synthetic_device_key,
    is_platform_chipset_device_key,
    lookup_inventory_row,
    platform_chipset_crash_attention,
    refresh_model_culprit_fields,
    resolve_crash_culprit_context,
    _culprit_info_row_is_placeholder,
    _driver_name_from_recommendation,
    _filter_possible_drivers_list,
    _infer_driver_vendor,
    _recommendation_applies_to_system,
)

"""
    needle = "from crash_report_timeline import ("
    if needle not in text:
        raise SystemExit("crash_report_timeline import anchor not found")
    idx = text.index(needle)
    end_idx = text.index("\n)\n", idx) + len("\n)\n")
    text = text[:end_idx] + "\n" + import_block + text[end_idx:]

    SRC.write_text(text, encoding="utf-8")
    print(f"Updated {SRC}")


if __name__ == "__main__":
    main()
