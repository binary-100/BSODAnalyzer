"""Regression tests for facade re-exports and runtime paths missed by offscreen GUI tests."""

from __future__ import annotations

import bsod_analyzer as core
import driver_catalog as dc
import firmware_catalog as fw
from gui_mixin_catalog_scan import GuiCatalogScanMixin
from gui_test_harness import minimal_fmt_args, report_contains


def test_driver_catalog_reexports_slug_for_oem_api() -> None:
    slug = dc._slug_for_oem_api("MAG B550 TOMAHAWK")
    assert slug
    assert " " not in slug


def test_firmware_support_links_uses_oem_slug() -> None:
    links = fw.get_firmware_support_links(
        {
            "system_manufacturer": "Micro-Star International Co., Ltd.",
            "baseboard_manufacturer": "Micro-Star International Co., Ltd.",
            "baseboard_product": "MAG B550 TOMAHAWK",
        }
    )
    assert any("msi.com" in (link.get("url") or "").lower() for link in links)


def test_crash_report_format_parse_json_date_available() -> None:
    import crash_report_format as crfmt

    assert crfmt._parse_json_date("2020-06-15") == "2020-06-15"


def test_format_output_renders_bios_driver_dates() -> None:
    fa = list(minimal_fmt_args())
    fa[13] = {
        "bios": {"manufacturer": "Dell", "version": "A01", "date": "2020-06-15"},
        "drivers": [{"name": "Intel NIC", "version": "1.0", "date": "2020-01-01"}],
    }
    report = core.format_output_from_fmt_args(tuple(fa), include_technical_details=True)
    assert "BIOS Date: 2020-06-15" in report
    assert "Date: 2020-01-01" in report


def test_format_output_technical_minidump_path() -> None:
    fa = list(minimal_fmt_args())
    fa[0] = [{"type": "BugCheck", "time": "2025-01-01 12:00:00", "code": "0xD1", "p1": "0"}]
    fa[1] = [{"name": "minidump.dmp", "path": "C:/x", "time": "2025-01-01 12:00:00"}]
    fa[4] = {"faulting_driver": "nvlddmkm.sys", "dumps_analyzed": 1}
    report = core.format_output_from_fmt_args(tuple(fa), include_technical_details=True)
    assert "Kernel minidumps:" in report

    fa = list(minimal_fmt_args())
    # slot 12 is app_crash_events (Event 1000); slot 3 is app_dumps (files on disk)
    fa[12] = [
        {
            "time": "2025-01-01 12:00:00",
            "application": "TestApp.exe",
            "module": "test.dll",
            "exception_code": "0xC0000005",
        }
    ]
    report = core.format_output_from_fmt_args(tuple(fa), include_technical_details=True)
    assert "APPLICATION CRASHES" in report
    assert report_contains(report, "Access violation")


def test_driver_scan_progress_label_on_instance() -> None:
    host = GuiCatalogScanMixin()
    assert host._driver_scan_progress_label("Checked 2/10 devices") == "Checked 2/10 devices"


def test_format_catalog_package_label_with_date() -> None:
    from gui_mixin_catalog_packages import GuiCatalogPackagesMixin

    host = GuiCatalogPackagesMixin()
    label = host._format_catalog_package_label(
        "Realtek USB Audio",
        "6.0.9700.1",
        "2024-03-15",
    )
    assert "Realtek USB Audio" in label
    assert "6.0.9700.1" in label
    assert "2024-03-15" in label
