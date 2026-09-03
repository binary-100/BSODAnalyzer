"""Tests for SSD vendor firmware registry and parsers."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import driver_catalog as dc
import firmware_catalog as fwcat
import firmware_ssd_vendors as fsv


FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _samsung_fixture_html() -> str:
    return (FIXTURES / "samsung_tools_ssd_snippet.html").read_text(encoding="utf-8")


def test_samsung_990_pro_parses_installed_revision() -> None:
    row = fsv.fetch_vendor_ssd_firmware(
        "samsung",
        "Samsung SSD 990 PRO 4TB",
        html=_samsung_fixture_html(),
    )
    assert row is not None
    assert row["version"] == "8B2QJXD7"
    assert not row["coverage_check_failed"]
    vs = dc.compare_firmware_versions("8B2QJXD7", row["version"])
    assert vs == "same"


def test_samsung_970_evo_fixture_profile() -> None:
    prof = next(p for p in fsv.SSD_REFERENCE_PROFILES if "970 EVO" in p.model)
    out = fsv.audit_reference_profile(prof, html_cache={"samsung": _samsung_fixture_html()})
    assert out["status"] == "up_to_date"
    assert out["vendor_row"]["version"] == "2B2QEXM7"


def test_distinctive_tokens_skip_vendor_name() -> None:
    tokens = fsv._distinctive_tokens("Samsung SSD 990 PRO 4TB")
    assert tokens[0] == "990"
    assert "samsung" not in tokens


def test_seagate_hybrid_parses_fixture_and_compares() -> None:
    html = (FIXTURES / "seagate_download_finder_st2000lx_snippet.html").read_text(encoding="utf-8")
    row = fsv.fetch_vendor_ssd_firmware(
        "seagate",
        "ST2000LX001-1RG174",
        html=html,
        storage_class="hybrid_hdd",
    )
    assert row is not None
    assert row["version"] == "CC44"
    assert not row["coverage_check_failed"]
    vs = dc.compare_firmware_versions("CC43", row["version"])
    assert vs in ("newer", "unknown")


def test_seagate_hybrid_without_serial_is_serial_required() -> None:
    row = fsv.fetch_vendor_ssd_firmware(
        "seagate",
        "ST2000LX001-1RG174",
        html="",
        storage_class="hybrid_hdd",
    )
    assert row is not None
    assert row["coverage_check_failed"]
    assert row["coverage_reason"] == "serial_required"


def test_coverage_gap_messages_are_specific() -> None:
    assert "blocked" not in fsv.coverage_gap_message("parse_failed", "Samsung").lower()
    assert "desktop utility" in fsv.coverage_gap_message("utility_only", "Kingston").lower()


def test_build_ssd_offers_samsung_same_from_fixture() -> None:
    drives = [{
        "model": "Samsung SSD 990 PRO 4TB",
        "firmware_revision": "8B2QJXD7",
        "vendor_key": "samsung",
    }]
    with mock.patch.object(
        fwcat,
        "_fetch_vendor_ssd_firmware",
        return_value={
            "title": "Samsung firmware (Samsung SSD 990 PRO 4TB)",
            "version": "8B2QJXD7",
            "url": "https://semiconductor.samsung.com/consumer-storage/support/tools/",
            "notes": "test",
            "coverage_check_failed": False,
        },
    ), mock.patch.object(fwcat, "fetch_mscatalog_storage_firmware_offers", return_value=[]), mock.patch.object(
        dc, "fetch_storage_driver_store_offers", return_value=[]
    ), mock.patch.object(fwcat, "fetch_windows_update_storage_firmware", return_value=None):
        offers = fwcat.build_ssd_firmware_offers(drives, [])
    assert offers
    assert offers[0]["vs_installed"] == "same"
    assert not offers[0].get("coverage_check_failed")


def test_all_reference_profiles_have_registry_entry() -> None:
    for prof in fsv.SSD_REFERENCE_PROFILES:
        assert prof.vendor_key in fsv.SSD_VENDOR_REGISTRY, prof.vendor_key


def test_registry_covers_wmi_inferred_vendors() -> None:
    expected = {
        "samsung", "wd", "sandisk", "crucial", "intel", "kingston",
        "kioxia", "toshiba", "seagate", "skhynix", "adata", "micron",
        "corsair", "phison", "siliconpower", "teamgroup",
    }
    assert expected <= set(fsv.SSD_VENDOR_REGISTRY.keys())


if __name__ == "__main__":
    test_samsung_990_pro_parses_installed_revision()
    test_samsung_970_evo_fixture_profile()
    test_distinctive_tokens_skip_vendor_name()
    test_seagate_hybrid_parses_fixture_and_compares()
    test_seagate_hybrid_without_serial_is_serial_required()
    test_coverage_gap_messages_are_specific()
    test_build_ssd_offers_samsung_same_from_fixture()
    test_all_reference_profiles_have_registry_entry()
    test_registry_covers_wmi_inferred_vendors()
    print("OK")
