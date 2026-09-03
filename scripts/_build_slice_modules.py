"""One-shot builder for catalog_offer_compare + catalog_mscatalog_queries slices."""
from __future__ import annotations

from pathlib import Path

APP = Path(__file__).resolve().parents[1]

LAZY_FUNCS = (
    "_offer_download_kind",
    "_offer_version_from_fields",
    "_is_primary_gpu_display_manufacturer_authoritative",
    "resolve_vendor_package_download_url",
)


def patch_lazy(source: str) -> str:
    for name in LAZY_FUNCS:
        source = source.replace(f"{name}(", f'_dc("{name}")(')
    return source


header = '''\
"""Per-offer compare, verification, and uncertain-resolution (from driver_catalog)."""

from __future__ import annotations

import driver_version_identity as dvi
import oem_effective_version as oev

from catalog_device_context import (
    _ctx_device_label,
    _ctx_is_amd_chipset_platform_row,
    _ctx_is_bluetooth_radio_device,
    _ctx_is_intel_chipset_platform_row,
    _ctx_is_wifi_radio_device,
    _device_is_amd_chipset_plumbing,
    _device_is_intel_chipset_plumbing,
    _device_is_intel_me_device,
)
from catalog_device_profiles import (
    _load_amd_adrenalin_installed_version,
    _load_amd_chipset_suite_installed_version,
    _load_intel_chipset_suite_installed_version,
    _load_intel_me_installed_version,
    _load_intel_wireless_installed_version,
    _load_nvidia_branch_installed_version,
    _load_realtek_ethernet_installed_version,
)
from catalog_mscatalog_session import _INSTALL_PROBE_CACHE, is_quick_check_mode
from catalog_oem_filters import _reject_oem_radio_wifi_bt_cross_mismatch
from catalog_offer_pipeline import (
    _SAME_WITHOUT_VERSION_NOTE,
    _UNVERIFIED_NEWER_NOTE,
    _append_compare_note,
    _offer_installability_rank,
    offer_source_sort_tier,
)
from catalog_offer_status import _offer_is_intel_chipset_inf
from catalog_realtek_queries import _soften_stale_realtek_wdm_oem_compare
from catalog_row_rejects import (
    _catalog_hwid_mismatch_note,
    _catalog_row_hwid_matches_ctx,
    _catalog_row_hwid_strict_matches_ctx,
    _realtek_device_component_role,
    _realtek_nic_mscatalog_trusted,
    _realtek_wdm_mscatalog_trusted,
)
from catalog_scoring import (
    _looks_like_amd_adrenalin_version,
    _looks_like_amd_chipset_package_version,
    compare_driver_to_installed,
)


def _dc(name: str):
    """Lazy driver_catalog lookup — avoids import cycles during module load."""
    import driver_catalog as dc

    return getattr(dc, name)


_DOWNLOAD_EXTENSIONS = (".exe", ".msi", ".cab", ".zip", ".inf", ".msu", ".7z")


'''

footer = '''
__all__ = [
    "_alternate_installed_baselines",
    "_apply_dual_baseline_gate",
    "_apply_update_reporting_policy",
    "_find_corroborating_offer",
    "_inherit_verification_trust",
    "_microsoft_hwid_verified_for_row",
    "_offer_compare_version",
    "_offer_has_installable_package",
    "_offer_trusted_for_confident_newer",
    "_probe_offer_install_path",
    "_recompare_offer_row",
    "_scheme_split_device_for_dual_baseline",
    "_try_resolve_uncertain_offer",
]
'''

msc_header = '''\
"""Microsoft Update Catalog search query builders (from driver_catalog)."""

from __future__ import annotations

import re

from catalog_device_context import _device_is_intel_me_device
from catalog_oem_live import _oem_search_keywords
from catalog_realtek_queries import _realtek_uad_catalog_queries
from catalog_row_rejects import _GENERIC_PNP_DEVICE_LABELS


'''

msc_footer = '''
__all__ = [
    "_batch_mscatalog_queries_for_ctx",
    "_catalog_search_queries_for_ctx",
    "_intel_mscatalog_queries",
    "_is_hwid_query",
    "_mediatek_mscatalog_queries",
]
'''


def main() -> None:
    compare_body = patch_lazy((APP / "_extract_compare.txt").read_text(encoding="utf-8"))
    (APP / "catalog_offer_compare.py").write_text(header + compare_body + footer, encoding="utf-8")

    msc_body = (APP / "_extract_mscatalog.txt").read_text(encoding="utf-8")
    (APP / "catalog_mscatalog_queries.py").write_text(msc_header + msc_body + msc_footer, encoding="utf-8")
    print("built catalog_offer_compare.py and catalog_mscatalog_queries.py")


if __name__ == "__main__":
    main()
