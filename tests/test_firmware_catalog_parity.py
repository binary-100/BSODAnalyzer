"""Firmware parity: OEM dates, SSD coverage-gap offers."""

from __future__ import annotations

import os
import sys
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import driver_catalog as dc
import firmware_catalog as fwcat


def test_offer_from_row_normalizes_dell_date() -> None:
    offer = fwcat._offer_from_row(
        {"title": "BIOS Update", "version": "1.2.3", "date": "February 02, 2026", "url": "https://x"},
        "OEM (Dell)",
        "1.0.0",
    )
    assert offer["date"] == "2026-02-02"
    assert "February 0" not in offer["date"]


def test_firmware_coverage_gap_offer_fields() -> None:
    o = fwcat._firmware_coverage_gap_offer(
        source_label="SSD (samsung)",
        title="Samsung SSD — 990 PRO",
        url="https://semiconductor.samsung.com/",
        model="Samsung SSD 990 PRO 1TB",
        installed="5B2Q",
        vendor_disp="samsung",
    )
    assert o["coverage_check_failed"] is True
    assert o["vs_installed"] == "uncertain"
    assert o["kind"] == "ssd"


def test_storage_firmware_not_classified_as_bios() -> None:
    row = {
        "title": "Samsung PM9A1 2 TB Solid State Drive Firmware Update",
        "category": "Firmware",
        "version": "3631.0129",
    }
    assert fwcat.is_storage_firmware_title(row)
    assert not fwcat.is_bios_catalog_row(row)


def test_bios_row_still_classified_as_bios() -> None:
    row = {
        "title": "Alienware m17 R5 UEFI BIOS Update",
        "category": "BIOS",
        "version": "1.28.0",
    }
    assert fwcat.is_bios_catalog_row(row)


def test_ssd_model_match_rejects_wrong_oem_sku() -> None:
    row = {"title": "Samsung PM9A1 2 TB Solid State Drive Firmware Update", "category": ""}
    assert not fwcat.is_storage_firmware_row(row, "Samsung SSD 990 PRO 4TB")


def test_ssd_model_match_accepts_matching_sku() -> None:
    row = {"title": "Samsung SSD 990 PRO Firmware Update", "category": ""}
    assert fwcat.is_storage_firmware_row(row, "Samsung SSD 990 PRO 4TB")


def test_reject_inbox_firmware_driver_for_retail_ssd() -> None:
    title = "Samsung Electronics Co., Ltd. Firmware Driver Update (10.0.10.39)"
    assert fwcat._reject_inbox_ssd_firmware_package(
        title, "10.0.10.39", "8B2QJXD7", vs_installed="unknown"
    )


def test_mscatalog_skips_inbox_firmware_driver() -> None:
    rows = [
        {
            "title": "Samsung Electronics Co., Ltd. Firmware Driver Update (10.0.10.39)",
            "version": "10.0.10.39",
            "date": "2026-05-22",
            "update_id": "abc",
        }
    ]

    class _Cps:
        @staticmethod
        def search_mscatalog_updates(*_a, **_k):
            return rows, ""

    with mock.patch.object(fwcat.dc, "_v6_catalog_enabled", lambda: True), mock.patch.object(
        fwcat.dc, "is_quick_check_mode", lambda: False
    ), mock.patch.object(
        fwcat.dc, "ensure_mscatalog_module_ready", lambda **_k: None
    ), mock.patch.dict(sys.modules, {"catalog_ps_module": _Cps()}):
        offers = fwcat.fetch_mscatalog_storage_firmware_offers(
            "Samsung SSD 990 PRO 4TB", "8B2QJXD7", "samsung"
        )
    assert offers == []


def test_build_ssd_offers_skips_mscatalog_inbox_reaches_vendor() -> None:
    drives = [
        {
            "model": "Samsung SSD 990 PRO 4TB",
            "firmware_revision": "8B2QJXD7",
            "vendor_key": "samsung",
        }
    ]
    inbox_offer = {
        "source": "microsoft",
        "source_label": "Microsoft Update Catalog",
        "title": "Samsung Electronics Co., Ltd. Firmware Driver Update (10.0.10.39)",
        "version": "10.0.10.39",
        "vs_installed": "unknown",
        "kind": "ssd",
    }
    with mock.patch.object(
        fwcat,
        "fetch_mscatalog_storage_firmware_offers",
        return_value=[inbox_offer],
    ), mock.patch.object(
        dc, "fetch_storage_driver_store_offers", return_value=[]
    ), mock.patch.object(
        fwcat, "fetch_windows_update_storage_firmware", return_value=None
    ), mock.patch.object(
        fwcat,
        "_fetch_vendor_ssd_firmware",
        return_value={
            "title": "Samsung SSD — Samsung SSD 990 PRO 4TB",
            "version": "",
            "url": "https://semiconductor.samsung.com/consumer-storage/support/tools/",
            "notes": "Use Samsung Magician",
            "coverage_check_failed": True,
        },
    ):
        offers = fwcat.build_ssd_firmware_offers(drives, [])
    assert len(offers) == 1
    assert offers[0].get("coverage_check_failed") is True
    assert offers[0].get("source") == "ssd_vendor"


def test_build_ssd_offers_falls_through_when_oem_unknown_only() -> None:
    """Weak OEM match (unknown compare) must not block MSCatalog/vendor fallback."""
    drives = [
        {
            "model": "Samsung SSD 990 PRO 4TB",
            "firmware_revision": "8B2QJXD7",
            "vendor_key": "samsung",
        }
    ]
    oem_rows = [
        (
            "Dell",
            {
                "title": "Samsung PM9A1 2 TB Solid State Drive Firmware Update",
                "version": "3631.0129",
                "url": "https://example.test/pm9a1",
            },
            "",
        )
    ]
    with mock.patch.object(
        fwcat, "fetch_mscatalog_storage_firmware_offers", return_value=[]
    ), mock.patch.object(
        dc, "fetch_storage_driver_store_offers", return_value=[]
    ), mock.patch.object(
        fwcat, "fetch_windows_update_storage_firmware", return_value=None
    ), mock.patch.object(
        fwcat,
        "_fetch_vendor_ssd_firmware",
        return_value={
            "title": "Samsung firmware (Samsung SSD 990 PRO 4TB)",
            "version": "8B2QJXD8",
            "url": "https://semiconductor.samsung.com/",
            "notes": "Parsed from Samsung support tools page.",
        },
    ):
        offers = fwcat.build_ssd_firmware_offers(drives, oem_rows)
    assert len(offers) == 1
    assert offers[0].get("source") == "ssd_vendor"
    assert offers[0].get("version") == "8B2QJXD8"


def test_build_ssd_offers_uses_coverage_gap_when_scrape_fails() -> None:
    drives = [
        {
            "model": "Samsung SSD 990 PRO 1TB",
            "firmware_revision": "5B2Q",
            "vendor_key": "samsung",
        }
    ]
    with mock.patch.object(
        fwcat,
        "_fetch_vendor_ssd_firmware",
        return_value={
            "title": "Samsung SSD — Samsung SSD 990 PRO 1TB",
            "version": "",
            "url": "https://semiconductor.samsung.com/",
            "notes": "Use Samsung Magician",
            "coverage_check_failed": True,
        },
    ), mock.patch.object(
        fwcat, "fetch_mscatalog_storage_firmware_offers", return_value=[]
    ), mock.patch.object(
        dc, "fetch_storage_driver_store_offers", return_value=[]
    ), mock.patch.object(
        fwcat, "fetch_windows_update_storage_firmware", return_value=None
    ):
        offers = fwcat.build_ssd_firmware_offers(drives, [])
    assert len(offers) == 1
    assert offers[0].get("coverage_check_failed") is True
    assert offers[0].get("vs_installed") == "uncertain"
    assert dc.summarize_offer_status(offers) == "uncertain"


def test_session_failures_include_firmware_ssd_coverage_gap() -> None:
    import vendor_endpoint_health as veh

    offers = [
        {
            "source": "ssd_vendor",
            "source_label": "SSD (samsung)",
            "coverage_check_failed": True,
            "vs_installed": "uncertain",
        }
    ]
    failed = veh.session_vendor_failures({}, firmware_offers=offers)
    assert any("ssd:" in v for v in failed)


def test_search_reuses_loaded_secondary_inventory() -> None:
    known = [
        {
            "key": "peripheral:046d:c081",
            "component": "Logitech G900 Gaming Mouse",
            "installed": "—",
            "vendor_key": "logitech",
        }
    ]
    with mock.patch(
        "firmware_peripheral_discovery.discover_secondary_firmware_devices"
    ) as discover:
        with mock.patch.object(
            fwcat,
            "build_secondary_firmware_offers",
            return_value=[{"kind": "peripheral", "target_key": known[0]["key"]}],
        ) as build_offers:
            devices, offers = fwcat.discover_and_build_secondary_offers(
                [],
                known_devices=known,
                target_keys=["peripheral:046d:c081"],
            )
            discover.assert_not_called()
            build_offers.assert_called_once()
            assert len(devices) == 1
            assert offers


def test_format_fw_installed_dual_line_for_peripheral() -> None:
    import bsod_gui_qt as gui

    text = gui.MainWindow._format_fw_installed_display(
        "10.0.26100.8521",
        {
            "key": "peripheral:046d:c081",
            "installed_source": "driver_version",
        },
    )
    assert "\n" in text
    assert "10.0.26100.8521" in text
    assert "verify in vendor app" in text


def test_firmware_target_unit_count() -> None:
    assert fwcat.firmware_target_unit_count(["bios"]) == 1
    assert (
        fwcat.firmware_target_unit_count(
            ["bios", "ssd:Samsung 990 PRO", "peripheral:046d:c081"]
        )
        == 3
    )
    assert fwcat.firmware_target_unit_count(["ssd:none"]) == 0
    assert fwcat.firmware_target_unit_count([]) == 0


def test_build_firmware_comparison_emits_checked_progress() -> None:
    messages: list[str] = []

    def _progress(msg: str) -> None:
        messages.append(msg)

    with mock.patch.object(dc, "extend_system_ctx_for_catalog", return_value={}), mock.patch.object(
        dc, "is_quick_check_mode", return_value=True
    ), mock.patch.object(dc, "_should_skip_online_driver_store", return_value=True), mock.patch.object(
        fwcat, "discover_and_build_secondary_offers", return_value=([], [])
    ):
        fwcat.build_firmware_comparison(
            {"version": "1.0", "date": ""},
            {},
            target_keys=["bios"],
            progress=_progress,
        )
    assert any("Checking 1 firmware component(s)" in m for m in messages)
    assert any(m.startswith("Checked 1/1") for m in messages)


if __name__ == "__main__":
    test_offer_from_row_normalizes_dell_date()
    test_firmware_coverage_gap_offer_fields()
    test_storage_firmware_not_classified_as_bios()
    test_bios_row_still_classified_as_bios()
    test_ssd_model_match_rejects_wrong_oem_sku()
    test_ssd_model_match_accepts_matching_sku()
    test_reject_inbox_firmware_driver_for_retail_ssd()
    test_mscatalog_skips_inbox_firmware_driver()
    test_build_ssd_offers_skips_mscatalog_inbox_reaches_vendor()
    test_build_ssd_offers_falls_through_when_oem_unknown_only()
    test_build_ssd_offers_uses_coverage_gap_when_scrape_fails()
    test_session_failures_include_firmware_ssd_coverage_gap()
    test_search_reuses_loaded_secondary_inventory()
    test_firmware_target_unit_count()
    test_build_firmware_comparison_emits_checked_progress()
    print("OK")
