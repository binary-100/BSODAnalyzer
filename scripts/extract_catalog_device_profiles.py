"""One-shot: move dual-version profile helpers from driver_catalog.py to catalog_device_profiles.py."""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "driver_catalog.py"
PROFILES = ROOT / "catalog_device_profiles.py"

NAMES = {
    "_device_vendor_key_from_dev",
    "_gpu_dual_version_applicable",
    "_best_catalog_offer_for_gpu_profile",
    "build_gpu_version_profile",
    "attach_gpu_version_profile",
    "format_gpu_installed_table_cell",
    "format_gpu_version_subtitle",
    "_chipset_component_short_label",
    "_collect_chipset_bundle_components",
    "_chipset_platform_profile_applicable",
    "build_chipset_platform_version_profile",
    "attach_chipset_platform_version_profile",
    "format_chipset_platform_installed_table_cell",
    "format_chipset_platform_version_subtitle",
    "_chipset_dual_version_applicable",
    "_chipset_profile_labels",
    "build_chipset_version_profile",
    "attach_chipset_version_profile",
    "format_chipset_installed_table_cell",
    "format_chipset_version_subtitle",
    "_dev_to_profile_ctx",
    "_looks_like_realtek_legacy_hda_version",
    "_realtek_audio_companion_version",
    "_realtek_dual_version_applicable",
    "build_realtek_audio_version_profile",
    "attach_realtek_audio_version_profile",
    "format_realtek_audio_installed_table_cell",
    "format_realtek_audio_version_subtitle",
    "_format_dual_version_installed_cell",
    "_format_dual_version_subtitle",
    "_looks_like_intel_me_component_version",
    "_format_realtek_nic_build_suffix",
    "_load_intel_me_installed_version",
    "_load_intel_wireless_installed_version",
    "_load_killer_suite_installed_version",
    "_load_broadcom_ethernet_installed_version",
    "_load_qualcomm_wireless_installed_version",
    "_load_realtek_ethernet_installed_version",
    "_network_dual_version_kind",
    "_intel_me_dual_version_applicable",
    "build_intel_me_version_profile",
    "attach_intel_me_version_profile",
    "format_intel_me_installed_table_cell",
    "format_intel_me_version_subtitle",
    "_network_dual_version_applicable",
    "build_network_version_profile",
    "attach_network_version_profile",
    "format_network_installed_table_cell",
    "format_network_version_subtitle",
    "attach_all_dual_version_profiles",
    "pick_dual_version_profile",
    "format_dual_version_installed_for_dev",
    "format_dual_version_subtitle_for_dev",
}

ASSIGN_NAMES = {
    "_CHIPSET_COMPONENT_ORDER_AMD",
    "_CHIPSET_COMPONENT_ORDER_INTEL",
}

MODULE_HEADER = '''\
"""Dual-version device profiles for GPU, chipset, audio, and network rows (extracted from driver_catalog)."""

from __future__ import annotations

import re

from catalog_scoring import (
    _load_amd_adrenalin_installed_version,
    _load_amd_chipset_suite_installed_version,
    _load_intel_chipset_suite_installed_version,
    _load_nvidia_branch_installed_version,
    _looks_like_amd_adrenalin_version,
    _looks_like_amd_chipset_package_version,
    _looks_like_amd_display_driver_version,
    _looks_like_intel_chipset_package_version,
    _looks_like_nvidia_branch_version,
    _looks_like_nvidia_internal_version,
    _looks_like_realtek_apo_version,
    _looks_like_realtek_nic_driver_version,
    _looks_like_realtek_wdm_version,
    _realtek_net_version_major,
    parse_driver_version,
)


def _dc(name: str):
    """Lazy driver_catalog lookup — avoids import cycles during module load."""
    import driver_catalog as dc

    return getattr(dc, name)


'''

_LAZY_DC_FUNCS = (
    "_offer_version_from_fields",
    "_device_is_amd_chipset_plumbing",
    "_device_is_intel_chipset_plumbing",
    "_device_is_intel_me_device",
    "_ctx_is_amd_device",
    "_ctx_is_intel_device",
    "_load_chipset_suite_installed_version",
    "_load_installed_package_versions",
    "_realtek_device_component_role",
    "_realtek_nic_version_tail",
    "_looks_like_chipset_package_version",
)


def _patch_lazy_refs(source: str) -> str:
    for name in _LAZY_DC_FUNCS:
        source = source.replace(f"{name}(", f"_dc('{name}')(")
    return source


def main() -> int:
    src = CATALOG.read_text(encoding="utf-8")
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
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id in ASSIGN_NAMES:
                    start = node.lineno - 1
                    end = node.end_lineno or node.lineno
                    extracted.append((start, "".join(lines[start:end]) + "\n"))
                    remove_ranges.append((start, end))

    expected = len(NAMES) + len(ASSIGN_NAMES)
    if len(extracted) != expected:
        found = set(NAMES)
        for node in tree.body:
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name in NAMES:
                found.discard(node.name)
        print(f"Missing defs: {sorted(found)}", file=sys.stderr)
        print(f"Got {len(extracted)} expected {expected}", file=sys.stderr)
        return 1

    if PROFILES.is_file() and "def build_gpu_version_profile(" in PROFILES.read_text(encoding="utf-8"):
        print("Already extracted — skip", file=sys.stderr)
        return 0

    extracted.sort(key=lambda x: x[0])
    body = "\n\n".join(c.rstrip() for _, c in extracted) + "\n"
    PROFILES.write_text(MODULE_HEADER + body, encoding="utf-8")

    new_lines = list(lines)
    for start, end in sorted(remove_ranges, reverse=True):
        del new_lines[start:end]
    CATALOG.write_text("".join(new_lines), encoding="utf-8")

    import_block = """from catalog_device_profiles import (
    attach_all_dual_version_profiles,
    attach_chipset_platform_version_profile,
    attach_chipset_version_profile,
    attach_gpu_version_profile,
    attach_intel_me_version_profile,
    attach_network_version_profile,
    attach_realtek_audio_version_profile,
    build_chipset_platform_version_profile,
    build_chipset_version_profile,
    build_gpu_version_profile,
    build_intel_me_version_profile,
    build_network_version_profile,
    build_realtek_audio_version_profile,
    format_chipset_installed_table_cell,
    format_chipset_platform_installed_table_cell,
    format_chipset_platform_version_subtitle,
    format_chipset_version_subtitle,
    format_dual_version_installed_for_dev,
    format_dual_version_subtitle_for_dev,
    format_gpu_installed_table_cell,
    format_gpu_version_subtitle,
    format_intel_me_installed_table_cell,
    format_intel_me_version_subtitle,
    format_network_installed_table_cell,
    format_network_version_subtitle,
    format_realtek_audio_installed_table_cell,
    format_realtek_audio_version_subtitle,
    pick_dual_version_profile,
)
"""
    cat = CATALOG.read_text(encoding="utf-8")
    anchor = "from catalog_offer_pipeline import ("
    if "from catalog_device_profiles import" not in cat:
        idx = cat.find(anchor)
        if idx == -1:
            print("Could not find insert point for profile imports", file=sys.stderr)
            return 1
        cat = cat[:idx] + import_block + cat[idx:]
        CATALOG.write_text(cat, encoding="utf-8")

    print(f"Extracted {len(extracted)} blocks into catalog_device_profiles.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
