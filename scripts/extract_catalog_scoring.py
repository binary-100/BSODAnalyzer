"""One-shot: move compare/scoring helpers from driver_catalog.py to catalog_scoring.py."""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "driver_catalog.py"
SCORING = ROOT / "catalog_scoring.py"

# Top-level names to extract (functions + one module-level regex).
NAMES = {
    "_looks_like_amd_chipset_package_version",
    "_looks_like_intel_chipset_package_version",
    "_intel_chipset_suite_build",
    "_intel_suite_vs_component_version_mismatch",
    "_looks_like_amd_adrenalin_version",
    "_looks_like_amd_display_driver_version",
    "_load_amd_chipset_suite_installed_version",
    "_load_intel_chipset_suite_installed_version",
    "_load_amd_adrenalin_installed_version",
    "_load_nvidia_branch_installed_version",
    "_looks_like_mediatek_uwd_version",
    "_ctx_skip_amd_adrenalin_compare_gate",
    "_ctx_is_wifi_radio_device",
    "_ctx_is_bluetooth_radio_device",
    "_looks_like_realtek_wdm_version",
    "_looks_like_realtek_apo_version",
    "_looks_like_realtek_nic_driver_version",
    "_realtek_net_version_major",
    "_realtek_nic_cross_scheme_equivalent",
    "_looks_like_windows_inbox_driver_version",
    "_version_prefix_family",
    "_version_schemes_compatible",
    "_looks_like_nvidia_branch_version",
    "_looks_like_nvidia_internal_version",
    "compare_driver_to_installed",
    "extract_version_from_text",
    "_firmware_version_compact",
    "compare_firmware_versions",
}

ASSIGN_NAMES = {"_MS_INBOX_VERSION_RE"}


def _patch_load_body(chunks: list[str]) -> list[str]:
    """Add one lazy loader if any moved function needs package versions."""
    needs = any("_load_installed_package_versions()" in c for c in chunks)
    if not needs:
        return chunks
    helper = (
        "def _load_installed_package_versions() -> dict[str, str]:\n"
        "    import driver_catalog as _dc\n"
        "    return _dc._load_installed_package_versions()\n"
    )
    if any("def _load_installed_package_versions() -> dict" in c for c in chunks):
        return chunks
    return [helper] + chunks


def _patch_ctx_label(chunks: list[str]) -> list[str]:
    joined = "\n".join(chunks)
    if "_ctx_device_label" not in joined:
        return chunks
    if any("def _ctx_device_label(" in c for c in chunks):
        return chunks
    helper = (
        "def _ctx_device_label(ctx: dict) -> str:\n"
        '    return (\n'
        '        ctx.get("device_label")\n'
        '        or ctx.get("device_name")\n'
        '        or ctx.get("target_device_name")\n'
        '        or ""\n'
        "    ).strip()\n"
    )
    return [helper] + chunks


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
            chunk = "".join(lines[start:end])
            extracted.append((start, chunk))
            remove_ranges.append((start, end))
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id in ASSIGN_NAMES:
                    start = node.lineno - 1
                    end = node.end_lineno or node.lineno
                    extracted.append((start, "".join(lines[start:end]) + "\n"))
                    remove_ranges.append((start, end))

    if len(extracted) != len(NAMES) + len(ASSIGN_NAMES):
        found = {n for n in NAMES}
        for node in tree.body:
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name in NAMES:
                found.discard(node.name)
        missing = sorted(found)
        print("Missing defs:", missing, file=sys.stderr)
        return 1

    extracted.sort(key=lambda x: x[0])
    chunks = [c.rstrip() for _, c in extracted]
    chunks = _patch_ctx_label(chunks)
    chunks = _patch_load_body(chunks)
    body = "\n\n".join(chunks) + "\n"

    scoring_src = SCORING.read_text(encoding="utf-8")
    if "def compare_driver_to_installed(" in scoring_src:
        print("Already extracted — skip", file=sys.stderr)
        return 0

    extra_imports = ""
    if "import driver_version_identity as dvi" not in scoring_src:
        extra_imports += "\nimport driver_version_identity as dvi\n"

    scoring_src = scoring_src.rstrip() + extra_imports + "\n\n" + body
    SCORING.write_text(scoring_src, encoding="utf-8")

    # Remove from driver_catalog (bottom-up so indices stay valid).
    new_lines = list(lines)
    for start, end in sorted(remove_ranges, reverse=True):
        del new_lines[start:end]

    new_src = "".join(new_lines)
    CATALOG.write_text(new_src, encoding="utf-8")

    # Add imports + re-exports after existing catalog_scoring import block.
    import_block = """from catalog_scoring import (
    compare_firmware_versions,
    compare_driver_to_installed,
    compare_versions,
    driver_date_is_trustworthy,
    extract_version_from_text,
    parse_driver_package_date,
    parse_driver_version,
    _looks_like_amd_adrenalin_version,
    _looks_like_amd_chipset_package_version,
    _looks_like_amd_display_driver_version,
    _looks_like_intel_chipset_package_version,
    _looks_like_nvidia_branch_version,
    _looks_like_nvidia_internal_version,
    _looks_like_realtek_nic_driver_version,
    _looks_like_realtek_wdm_version,
    _load_amd_adrenalin_installed_version,
    _load_amd_chipset_suite_installed_version,
    _load_intel_chipset_suite_installed_version,
    _load_nvidia_branch_installed_version,
    _realtek_nic_cross_scheme_equivalent,
    _version_schemes_compatible,
)
"""
    new_src = CATALOG.read_text(encoding="utf-8")
    old = """from catalog_scoring import (
    compare_versions,
    driver_date_is_trustworthy,
    parse_driver_package_date,
    parse_driver_version,
)
"""
    if old in new_src:
        new_src = new_src.replace(old, import_block, 1)
        CATALOG.write_text(new_src, encoding="utf-8")

    print(f"Extracted {len(extracted)} blocks into catalog_scoring.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
