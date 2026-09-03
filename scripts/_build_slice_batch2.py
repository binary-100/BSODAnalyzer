"""Build catalog_chipset_comparison.py and append best_* to catalog_offer_status."""
from __future__ import annotations

from pathlib import Path

APP = Path(__file__).resolve().parents[1]

CHIPSET_LAZY = (
    "fetch_amd_driver_offers",
    "fetch_intel_driver_offers",
    "fetch_oem_driver_offers",
    "_microsoft_catalog_task",
    "_amd_drivers_download_url",
    "_load_installed_package_versions",
)


def _patch_lazy(source: str) -> str:
    for name in CHIPSET_LAZY:
        source = source.replace(f"{name}(", f'_dc("{name}")(')
    return source


chipset_header = '''\
"""Chipset/platform comparison helpers (extracted from driver_catalog)."""

from __future__ import annotations

from datetime import datetime
from typing import Callable

from catalog_device_context import (
    _ctx_is_amd_chipset_platform_row,
    _ctx_is_intel_chipset_platform_row,
    _device_is_amd_chipset_plumbing,
    _pci_tokens_from_id,
)
from catalog_device_profiles import build_chipset_platform_version_profile
from catalog_offer_pipeline import _finalize_catalog_offers
from catalog_scoring import (
    _looks_like_amd_chipset_package_version,
    _looks_like_intel_chipset_package_version,
    compare_versions,
)


def _dc(name: str):
    """Lazy driver_catalog lookup — avoids import cycles during module load."""
    import driver_catalog as dc

    return getattr(dc, name)


'''

chipset_footer = '''
__all__ = [
    "_build_chipset_catalog_context",
    "_chipset_platform_oem_offers",
    "_load_chipset_suite_installed_version",
    "_looks_like_chipset_package_version",
    "_resolve_chipset_installed_version",
    "build_chipset_platform_comparison",
    "chipset_ms_catalog_limitation_note",
]
'''


def main() -> None:
    helpers = (APP / "_slice_helpers.txt").read_text(encoding="utf-8")
    chipset = _patch_lazy((APP / "_slice_chipset.txt").read_text(encoding="utf-8"))
    (APP / "catalog_chipset_comparison.py").write_text(
        chipset_header + helpers + "\n\n" + chipset + chipset_footer,
        encoding="utf-8",
    )

    best_body = (APP / "_slice_best.txt").read_text(encoding="utf-8")
    best_body = best_body.replace("_offer_version_from_fields(", '_dc("_offer_version_from_fields")(')

    status_path = APP / "catalog_offer_status.py"
    status = status_path.read_text(encoding="utf-8")
    if "def best_authoritative_offer" not in status:
        insert = status.find("\n__all__ = [")
        status = (
            status[:insert]
            + "\n\n"
            + best_body
            + "\n"
            + status[insert:].replace(
                '"summarize_offer_status",',
                '"summarize_offer_status",\n    "best_authoritative_offer",\n    "best_versioned_offer",',
            )
        )
        status = status.replace(
            'versioned = _dc("best_versioned_offer")(eligible)',
            "versioned = best_versioned_offer(eligible)",
        )
        status_path.write_text(status, encoding="utf-8")

    print("built catalog_chipset_comparison.py and updated catalog_offer_status.py")


if __name__ == "__main__":
    main()
