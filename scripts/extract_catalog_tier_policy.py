"""Extract tier/deferral/OEM-skip policy from driver_catalog.py → catalog_tier_policy.py."""

from __future__ import annotations

from pathlib import Path

APP = Path(__file__).resolve().parents[1]
CATALOG = APP / "driver_catalog.py"
OUT = APP / "catalog_tier_policy.py"

# Inclusive line range in driver_catalog.py (verify before re-run).
TIER_RANGE = (1356, 1551)

HEADER = '''\
"""Catalog tier/deferral/OEM-skip policy (extracted from driver_catalog)."""

from __future__ import annotations

from catalog_device_context import _device_is_chipset_plumbing
from catalog_offer_pipeline import (
    _finalize_catalog_offers,
    _installed_driver_date_from_ctx,
)
from catalog_scoring import compare_versions


def _dc(name: str):
    """Lazy driver_catalog lookup — avoids import cycles during module load."""
    import driver_catalog as dc

    return getattr(dc, name)


_NETWORK_VENDOR_KEYS = frozenset({"killer", "broadcom", "qualcomm", "mediatek"})


'''

FOOTER = '''
__all__ = [
    "_NETWORK_VENDOR_KEYS",
    "_ctx_gpu_or_network_catalog",
    "_ctx_is_chipset_catalog",
    "_is_informational_catalog_offer",
    "_is_manufacturer_catalog_offer",
    "_manufacturer_confident_newer_offer",
    "_manufacturer_gpu_lookup_uncertain",
    "_oem_disk_offers_stale_vs_installed",
    "_should_skip_oem_after_manufacturer_tier",
    "has_actionable_versioned_manufacturer_offer",
    "has_actionable_versioned_offer",
    "should_defer_microsoft_catalog",
]
'''

_LAZY = (
    "_offer_download_kind",
    "_offer_version_from_fields",
    "_is_oem_support_link_offer",
    "_is_primary_gpu_display_manufacturer_authoritative",
)


def _patch_lazy(source: str) -> str:
    for name in _LAZY:
        source = source.replace(f"{name}(", f'_dc("{name}")(')
    return source


def main() -> int:
    lines = CATALOG.read_text(encoding="utf-8").splitlines(keepends=True)
    start, end = TIER_RANGE
    body = _patch_lazy("".join(lines[start - 1 : end]))
    OUT.write_text(HEADER + body + "\n" + FOOTER, encoding="utf-8")
    print(f"Wrote {OUT.name} from driver_catalog.py lines {start}-{end}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
