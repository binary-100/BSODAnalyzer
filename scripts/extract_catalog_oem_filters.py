"""One-shot: extract OEM brand/reject filters from driver_catalog.py."""

from __future__ import annotations

import re
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
DC = APP / "driver_catalog.py"
OUT = APP / "catalog_oem_filters.py"

# 1-based inclusive line ranges to extract from driver_catalog.py
CONST_RANGES = [(1032, 1113)]
FUNC_RANGES = [
    (1732, 2097),  # brand + reject through realtek hd (excl. wdm soften helpers)
    (2126, 2199),  # radio hints through wifi/bt cross mismatch
    (2253, 2276),  # oem_radio_chip_mismatch only (keep mscatalog helpers in driver_catalog)
]

_DC_CALLS = (
    "_ctx_device_label",
    "_catalog_row_hwid_matches_ctx",
    "_system_pc_oem_tags",
    "_device_is_amd_chipset_plumbing",
    "_device_is_intel_chipset_plumbing",
    "_nvidia_is_audio_component",
    "_device_is_amd_audio",
    "_ctx_is_amd_device",
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

    body = "".join(chunks)
    body = _patch_dc_calls(body)

    header = '''"""OEM brand alignment and reject filters (extracted from driver_catalog)."""

from __future__ import annotations

import re

from catalog_oem_live import _is_generic_oem_support_row
from catalog_scoring import (
    _ctx_is_bluetooth_radio_device,
    _ctx_is_wifi_radio_device,
    _looks_like_amd_chipset_package_version,
    _looks_like_intel_chipset_package_version,
    _looks_like_windows_inbox_driver_version,
)


def _dc(name: str):
    """Lazy driver_catalog lookup — avoids import cycles during module load."""
    import driver_catalog as dc

    return getattr(dc, name)


'''

    OUT.write_text(header + body, encoding="utf-8")
    print(f"Wrote {OUT} ({len((header + body).splitlines())} lines approx)")

    # Remove extracted ranges from driver_catalog (reverse order)
    remove = sorted(CONST_RANGES + FUNC_RANGES, reverse=True)
    for start, end in remove:
        del lines[start - 1 : end]

    # Insert import after catalog_http block
    import_block = """from catalog_oem_filters import (
    _CATALOG_PACKAGE_BRAND_TOKENS,
    _DELL_OEM_INTERNAL_DRIVER_CLASSES,
    _OEM_AIRPLANE_MODE_HINTS,
    _OEM_PC_MAKER_UPDATE_APP_HINTS,
    _OEM_RADIO_CHIP_HINTS,
    _OEM_RADIO_CHIP_LABEL_TOKENS,
    _PC_OEM_BRAND_KEYS,
    _PLATFORM_SILICON_MANUFACTURER_HINTS,
    _STANDARD_PNP_MANUFACTURERS,
    _brand_identities_align,
    _ctx_label_has_radio_chip_hint,
    _device_brand_identities,
    _device_on_integrated_bus,
    _manufacturer_is_pc_system_oem,
    _manufacturer_is_platform_silicon_partner,
    _manufacturer_is_standard_or_ambiguous,
    _normalize_brand_token,
    _oem_package_title_is_bluetooth,
    _oem_package_title_is_wifi,
    _package_brand_identities,
    _pc_oem_catalog_may_target_device,
    _pnp_manufacturer_is_third_party,
    _reject_oem_airplane_mode_mismatch,
    _reject_oem_amd_chipset_on_component_inf,
    _reject_oem_application_on_driver_device,
    _reject_oem_audio_vendor_mismatch,
    _reject_oem_intel_chipset_on_component_inf,
    _reject_oem_package_brand_mismatch,
    _reject_oem_pc_maker_on_third_party_device,
    _reject_oem_pc_maker_update_application,
    _reject_oem_radio_chip_mismatch,
    _reject_oem_radio_wifi_bt_cross_mismatch,
    _reject_oem_realtek_hd_on_inbox_hd_controller,
)

"""
    text = "".join(lines)
    needle = "from catalog_http import (\n"
    if needle not in text:
        raise SystemExit("catalog_http import anchor not found")
    idx = text.index(needle)
    end_idx = text.index("\n)\n", idx) + len("\n)\n")
    text = text[:end_idx] + "\n" + import_block + text[end_idx:]

    DC.write_text(text, encoding="utf-8")
    print(f"Updated {DC}")


if __name__ == "__main__":
    main()
