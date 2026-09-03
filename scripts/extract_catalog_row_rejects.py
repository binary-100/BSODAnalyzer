"""One-shot: extract shared catalog row reject + HWID helpers from driver_catalog.py."""

from __future__ import annotations

import re
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
DC = APP / "driver_catalog.py"
OUT = APP / "catalog_row_rejects.py"

# 1-based inclusive line ranges
CONST_RANGES = [
    (1007, 1022),  # excluded pnp + generic labels
    (1025, 1067),  # oem title patterns, security, firmware, amd phrases
    (1108, 1121),  # pnp classes block amd system
]
FUNC_RANGES = [
    (1237, 1414),  # amd bulk + vendor class mismatch
    (1715, 1759),  # microsoft catalog source + mediatek reject
    (1762, 2041),  # realtek role/reject (through oem net family)
    (2245, 2437),  # oem tags, hwid helpers, shared + mscatalog reject
]

_DC_CALLS = (
    "_ctx_device_label",
    "_ctx_is_amd_device",
    "_device_is_amd_chipset_plumbing",
    "_device_is_amd_media",
    "_offer_version_from_fields",
)


def _patch_dc_calls(text: str) -> str:
    for name in _DC_CALLS:
        text = re.sub(rf"(?<![.\w]){re.escape(name)}\(", f'_dc("{name}")(', text)
    return text


def main() -> None:
    lines = DC.read_text(encoding="utf-8").splitlines(keepends=True)
    chunks: list[str] = []
    for start, end in CONST_RANGES + FUNC_RANGES:
        chunks.extend(lines[start - 1 : end])

    body = _patch_dc_calls("".join(chunks))

    header = '''"""Catalog row rejection, HWID matching, and MSCatalog row filters (extracted from driver_catalog)."""

from __future__ import annotations

import re

import driver_version_identity as dvi
from catalog_oem_filters import (
    _reject_oem_airplane_mode_mismatch,
    _reject_oem_amd_chipset_on_component_inf,
    _reject_oem_application_on_driver_device,
    _reject_oem_audio_vendor_mismatch,
    _reject_oem_intel_chipset_on_component_inf,
    _reject_oem_pc_maker_on_third_party_device,
    _reject_oem_pc_maker_update_application,
    _reject_oem_radio_chip_mismatch,
    _reject_oem_realtek_hd_on_inbox_hd_controller,
)
from catalog_scoring import (
    compare_versions,
    parse_driver_version,
    _looks_like_amd_adrenalin_version,
    _looks_like_mediatek_uwd_version,
    _looks_like_realtek_nic_driver_version,
    _looks_like_realtek_wdm_version,
    _realtek_net_version_major,
)


def _dc(name: str):
    """Lazy driver_catalog lookup — avoids import cycles during module load."""
    import driver_catalog as dc

    return getattr(dc, name)


'''

    OUT.write_text(header + body, encoding="utf-8")
    print(f"Wrote {OUT} ({len((header + body).splitlines())} lines approx)")

    remove = sorted(CONST_RANGES + FUNC_RANGES, reverse=True)
    for start, end in remove:
        del lines[start - 1 : end]

    import_block = """from catalog_row_rejects import (
    _AMD_MEDIA_DRIVER_PHRASE,
    _AMD_SYSTEM_DRIVER_PHRASE,
    _DRIVER_SCAN_EXCLUDED_PNP_CLASSES,
    _FIRMWARE_CATALOG_TITLE_KEYWORDS,
    _GENERIC_PNP_DEVICE_LABELS,
    _PC_OEM_TITLE_PATTERNS,
    _PNP_CLASSES_BLOCK_AMD_SYSTEM,
    _SECURITY_AV_VENDOR_KEYWORDS,
    _catalog_hwid_mismatch_note,
    _catalog_row_hwid_blob,
    _catalog_row_hwid_matches_ctx,
    _catalog_row_hwid_strict_matches_ctx,
    _catalog_title_cross_oem_mismatch,
    _catalog_title_is_firmware_package,
    _catalog_title_is_security_software,
    _catalog_title_pc_oem_tags,
    _is_microsoft_catalog_row_source,
    _mscatalog_rows_hwid_first_keep,
    _normalize_catalog_row_for_reject,
    _prioritize_mscatalog_scored_rows,
    _realtek_catalog_row_is_companion_component,
    _realtek_catalog_row_is_wdm_codec,
    _realtek_device_component_role,
    _realtek_nic_mscatalog_trusted,
    _realtek_nic_public_build_suffix,
    _realtek_nic_same_oem_family,
    _realtek_nic_version_tail,
    _realtek_wdm_mscatalog_codec_rows_to_keep,
    _realtek_wdm_mscatalog_trusted,
    _reject_amd_bulk_catalog_row,
    _reject_mediatek_mscatalog_spurious,
    _reject_mscatalog_row_for_ctx,
    _reject_realtek_catalog_row,
    _reject_realtek_oem_net_family_mismatch,
    _reject_vendor_driver_class_mismatch,
    _shared_catalog_row_rejects,
    _system_pc_oem_tags,
)

"""
    text = "".join(lines)
    needle = "from catalog_oem_filters import (\n"
    if needle not in text:
        raise SystemExit("catalog_oem_filters import anchor not found")
    idx = text.index(needle)
    end_idx = text.index("\n)\n", idx) + len("\n)\n")
    text = text[:end_idx] + "\n" + import_block + text[end_idx:]

    DC.write_text(text, encoding="utf-8")
    print(f"Updated {DC}")


if __name__ == "__main__":
    main()
