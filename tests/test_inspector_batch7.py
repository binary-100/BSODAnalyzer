"""v6 Batch 7 — scan mode clarity, uncertain inspector, firmware fusion (E22–E25)."""

from __future__ import annotations

from unittest import mock

import driver_catalog as dc
import firmware_catalog as fc


def test_catalog_scan_mode_quick_vs_full() -> None:
    dc.configure_catalog(quick_check=True)
    try:
        quick = dc.catalog_scan_mode_summary(quick_check=True, gui_mode=True)
        assert quick["mode"] == "quick check"
        assert "Microsoft Update Catalog search" in quick["detail"]
    finally:
        dc.configure_catalog(quick_check=False)

    full = dc.catalog_scan_mode_summary(quick_check=False, gui_mode=True)
    assert full["mode"] == "full scan"
    assert "MSCatalogLTS" in full["detail"]

    install = dc.catalog_scan_mode_summary(full_install=True, quick_check=True, gui_mode=True)
    assert install["mode"] == "full install scan"


def test_build_uncertain_inspector_summary_lists_sources() -> None:
    offers = [
        {
            "source": "oem",
            "source_label": "OEM (Dell)",
            "version": "2.18.0",
            "vs_installed": "unknown",
            "compare_note": "Date-only OEM package",
        },
        {
            "source": "microsoft",
            "source_label": "Microsoft Update Catalog",
            "version": "2.19.1",
            "vs_installed": "uncertain",
            "source_conflict": True,
        },
    ]
    text = dc.build_uncertain_inspector_summary(offers, "2.17.0", status="unknown")
    assert "Installed: 2.17.0" in text
    assert "OEM (Dell)" in text
    assert "Microsoft Update Catalog" in text
    assert "source conflict" in text.lower()


def test_finalize_catalog_offers_firmware() -> None:
    offers = [
        {
            "source": "oem_firmware",
            "source_label": "OEM (HP)",
            "title": "System BIOS",
            "version": "F.30",
            "kind": "bios",
        },
        {
            "source": "microsoft",
            "source_label": "Microsoft Update Catalog",
            "title": "System Firmware Update",
            "version": "F.31",
            "kind": "bios",
        },
    ]
    out = dc.finalize_catalog_offers(offers, "F.29", firmware=True)
    assert len(out) >= 2
    assert all(o.get("vs_installed") for o in out)


def test_finalize_firmware_offers_merges_ssd_and_bios() -> None:
    offers = [
        {
            "source": "oem_firmware",
            "source_label": "OEM",
            "title": "BIOS",
            "version": "1.0.1",
            "kind": "bios",
        },
        {
            "source": "ssd_vendor",
            "source_label": "SSD (samsung)",
            "title": "Samsung 990 PRO firmware",
            "version": "5B2QGXA7",
            "kind": "ssd",
            "installed_firmware": "5B2QGXA6",
        },
        {
            "source": "utility",
            "source_label": "Utility",
            "title": "Samsung Magician",
            "kind": "utility",
        },
    ]
    out = fc.finalize_firmware_offers(offers, bios_installed="1.0.0", bios_date="2024-01-01")
    kinds = {o.get("kind") for o in out}
    assert "bios" in kinds
    assert "ssd" in kinds
    assert "utility" in kinds


def test_collect_oem_storage_firmware_rows_filters_storage() -> None:
    row = {"title": "Samsung SSD PM9A1 Firmware Update", "category": "Storage", "version": "GXA7"}
    with mock.patch.object(dc, "get_dell_oem_rows", return_value=([row], "https://dell.com")):
        collected = fc._collect_oem_storage_firmware_rows(
            {"system_manufacturer": "Dell Inc."},
        )
    assert len(collected) == 1
    assert collected[0][0] == "Dell"


def test_mscatalog_storage_skipped_in_quick_check() -> None:
    dc.configure_catalog(quick_check=True)
    try:
        assert fc.fetch_mscatalog_storage_firmware_offers("Samsung 990 PRO", "5B2Q", "samsung") == []
    finally:
        dc.configure_catalog(quick_check=False)


def test_build_ssd_uncertain_inspector_groups_by_drive() -> None:
    offers = [
        {
            "kind": "ssd",
            "source_label": "Microsoft Update Catalog",
            "version": "7B2QJXD7",
            "vs_installed": "uncertain",
            "installed_model": "Samsung 990 PRO",
            "installed_firmware": "5B2QGXA7",
            "search_query": "990 ssd firmware",
        },
        {
            "kind": "ssd",
            "source_label": "Microsoft Update Catalog",
            "version": "62033100",
            "vs_installed": "newer",
            "installed_model": "WD_BLACK SN850X",
            "installed_firmware": "62033100",
            "search_query": "sn850 nvme firmware",
        },
    ]
    drives = [
        {"model": "Samsung 990 PRO", "firmware_revision": "5B2QGXA7"},
        {"model": "WD_BLACK SN850X", "firmware_revision": "62033100"},
    ]
    text = fc.build_ssd_uncertain_inspector_summary(
        offers,
        drives,
        status="uncertain",
        focus_model="Samsung 990 PRO",
    )
    assert "Samsung 990 PRO" in text
    assert "990 ssd firmware" in text
    assert "WD_BLACK" not in text


def test_firmware_utility_inspector_summary() -> None:
    text = fc.build_firmware_utility_inspector_summary(
        [
            {
                "source": "utility",
                "source_label": "Device utility",
                "title": "Samsung Magician",
                "version": "—",
                "url": "https://semiconductor.samsung.com/consumer-storage/support/tools/",
                "notes": "Use Samsung Magician to compare firmware.",
                "kind": "utility",
            }
        ],
        component_label="Samsung 990 PRO",
        kind="ssd",
    )
    assert "Magician" in text
    assert "Steps:" in text
    assert fc.offers_are_utility_only([{"kind": "utility", "title": "x", "url": "http://a"}])


def test_bios_uncertain_inspector_summary() -> None:
    text = fc.build_bios_uncertain_inspector_summary(
        [
            {
                "kind": "bios",
                "source_label": "OEM (Dell)",
                "version": "1.18.0",
                "vs_installed": "unknown",
            }
        ],
        "1.17.0",
        status="unknown",
        system_ctx={"system_manufacturer": "Dell Inc.", "system_model": "Alienware m17"},
    )
    assert "System BIOS" in text
    assert "Alienware m17" in text


if __name__ == "__main__":
    test_catalog_scan_mode_quick_vs_full()
    test_build_uncertain_inspector_summary_lists_sources()
    test_finalize_catalog_offers_firmware()
    test_finalize_firmware_offers_merges_ssd_and_bios()
    test_collect_oem_storage_firmware_rows_filters_storage()
    test_mscatalog_storage_skipped_in_quick_check()
    test_build_ssd_uncertain_inspector_groups_by_drive()
    test_firmware_utility_inspector_summary()
    test_bios_uncertain_inspector_summary()
    print("Batch 7 inspector tests OK")
