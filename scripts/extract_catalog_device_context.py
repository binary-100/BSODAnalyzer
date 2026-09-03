"""Extract / refresh catalog_device_context.py — phase 1 stays in place; phase 2 from driver_catalog."""

from __future__ import annotations

import re
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
DC = APP / "driver_catalog.py"
OUT = APP / "catalog_device_context.py"

PHASE2_FUNC = [
    (1339, 1447),
    (1708, 1975),
    (3764, 3798),
    (3854, 3919),
]

HEADER = '''"""Device context classification, builders, and driver-scan scope (from driver_catalog)."""

from __future__ import annotations

import re

from catalog_scoring import _looks_like_realtek_wdm_version

_DRIVER_SCAN_EXCLUDED_PNP_CLASSES = frozenset({"firmware"})

'''

FOOTER = '''
__all__ = [
    "_DRIVER_SCAN_EXCLUDED_PNP_CLASSES",
    "_ctx_device_label",
    "_ctx_is_amd_device",
    "_device_is_amd_chipset_plumbing",
    "_ctx_is_intel_device",
    "_device_is_intel_chipset_plumbing",
    "_intel_driver_hint_from_ctx",
    "_device_is_intel_me_device",
    "_device_is_chipset_plumbing",
    "_ctx_is_chipset_component_plumbing",
    "_device_is_amd_media",
    "_device_is_amd_audio",
    "_nvidia_is_audio_or_usb_component",
    "_nvidia_is_audio_component",
    "_nvidia_gpu_driver_lookup_applicable",
    "_nvidia_ctx_eligible",
    "_ctx_is_amd_chipset_platform_row",
    "_ctx_is_intel_chipset_platform_row",
    "is_driver_scan_excluded_ctx",
    "is_driver_scan_excluded_device",
    "_pci_tokens_from_id",
    "_infer_vendor_from_device_name",
    "_infer_pnp_class_for_device",
    "_lookup_pnpsigned_version_from_index",
    "_version_from_pnpsigned_inventory",
    "_resolve_primary_installed_version",
    "_apply_realtek_parent_hwid_ctx",
    "get_device_context",
    "get_device_context_for_name",
]
'''


def _phase1_body() -> str:
    text = OUT.read_text(encoding="utf-8")
    start = text.find("_AMD_CHIPSET_PLUMBING_NAME_PARTS")
    end = text.find("__all__")
    if start < 0 or end < 0:
        raise SystemExit("catalog_device_context.py missing phase-1 body")
    return text[start:end].rstrip() + "\n\n\n"


def _extract_ranges(lines: list[str], ranges: list[tuple[int, int]]) -> str:
    chunks: list[str] = []
    for start, end in ranges:
        chunks.extend(lines[start - 1 : end])
    return "".join(chunks)


def _patch_phase2(body: str) -> str:
    body = body.replace(
        "    for row in _get_pnpsigned_driver_rows():",
        "    import driver_catalog as _dc_catalog\n\n"
        "    for row in _dc_catalog._get_pnpsigned_driver_rows():",
        1,
    )
    body = body.replace(
        '    """PnP instance, hardware IDs, GPU rows, OEM tag — for catalog queries."""',
        '    """PnP instance, hardware IDs, GPU rows, OEM tag — for catalog queries."""\n'
        "    from bsod_analyzer import (\n"
        "        DRIVER_TO_HARDWARE,\n"
        "        _find_pnp_entity_by_device_name,\n"
        "        _infer_driver_vendor,\n"
        "        find_culprit_devices,\n"
        "        lookup_inventory_row,\n"
        "    )",
        1,
    )
    body = body.replace(
        '    """Catalog context for a specific PnP device (generic drivers tab — no crash module)."""',
        '    """Catalog context for a specific PnP device (generic drivers tab — no crash module)."""\n'
        "    from bsod_analyzer import (\n"
        "        _extract_vendor_from_string,\n"
        "        _find_pnp_entity_by_device_name,\n"
        "        lookup_inventory_row,\n"
        "    )",
        1,
    )
    body = body.replace(
        '    """UAD codec/function rows may lack DeviceID — inherit parent HDAUDIO VEN_10EC."""',
        '    """UAD codec/function rows may lack DeviceID — inherit parent HDAUDIO VEN_10EC."""\n'
        "    from bsod_analyzer import _find_pnp_entity_by_device_name\n"
        "    from catalog_row_rejects import _realtek_device_component_role",
        1,
    )
    body = body.replace(
        "    vendor = _extract_vendor_from_string(combined)",
        "    from bsod_analyzer import _extract_vendor_from_string\n\n"
        "    vendor = _extract_vendor_from_string(combined)",
        1,
    )
    return body


def main() -> None:
    dc_lines = DC.read_text(encoding="utf-8").splitlines(keepends=True)
    phase1 = _phase1_body()
    phase2 = _patch_phase2(_extract_ranges(dc_lines, PHASE2_FUNC))
    OUT.write_text(HEADER + phase1 + phase2 + FOOTER, encoding="utf-8")
    total = len((phase1 + phase2).splitlines())
    print(f"Wrote {OUT} ({total} body lines)")


if __name__ == "__main__":
    main()
