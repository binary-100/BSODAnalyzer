"""Tests for parser-rot detection (empty extraction → session vendor failures)."""
from __future__ import annotations

import os
import sys
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bsod_hardware_wmi as hw
import driver_catalog as dc
import vendor_endpoint_health as veh
import vendor_fetch as vf


def _with_empty_cache(fn):
    cache = getattr(dc, "_VENDOR_SCRAPE_CACHE", None)
    saved = dict(cache) if isinstance(cache, dict) else {}
    try:
        if isinstance(cache, dict):
            cache.clear()
        return fn()
    finally:
        if isinstance(cache, dict):
            cache.clear()
            cache.update(saved)


def test_record_empty_extraction_tracked() -> None:
    vf.clear_session_diagnostics()
    vf.record_empty_extraction(
        "amd", "amd_download_center: page loaded but no version extracted"
    )
    details = vf.empty_extraction_details("amd")
    assert "amd" in details
    assert any("no version" in d for d in details["amd"])


def test_session_failures_include_empty_extraction() -> None:
    vf.clear_session_diagnostics()
    vf.record_empty_extraction("amd", "page loaded but no version extracted")

    def run():
        with mock.patch.object(hw, "amd_driver_lookup_applicable", return_value=True), \
             mock.patch.object(hw, "intel_driver_lookup_applicable", return_value=False), \
             mock.patch.object(hw, "nvidia_driver_lookup_applicable", return_value=False):
            return veh.session_vendor_failures({})

    failed = _with_empty_cache(run)
    assert "amd" in failed


def test_session_failures_include_coverage_check_failed_rows() -> None:
    vf.clear_session_diagnostics()
    rows = [
        {
            "device_name": "AMD Radeon",
            "offers": [
                {
                    "source_label": "Manufacturer (AMD)",
                    "coverage_check_failed": True,
                    "vs_installed": "uncertain",
                }
            ],
        }
    ]

    def run():
        with mock.patch.object(hw, "amd_driver_lookup_applicable", return_value=True), \
             mock.patch.object(hw, "intel_driver_lookup_applicable", return_value=False), \
             mock.patch.object(hw, "nvidia_driver_lookup_applicable", return_value=False):
            return veh.session_vendor_failures({}, driver_rows=rows)

    failed = _with_empty_cache(run)
    assert "amd" in failed


def test_successful_version_suppresses_empty_extraction() -> None:
    """If cache still holds a good version, don't nag about empty extraction."""
    vf.clear_session_diagnostics()
    vf.record_empty_extraction("amd", "later attempt empty")
    cache = dc._VENDOR_SCRAPE_CACHE
    key = "amd:graphics:test"
    cache[key] = ("26.6.4", "")
    try:
        with mock.patch.object(hw, "amd_driver_lookup_applicable", return_value=True), \
             mock.patch.object(hw, "intel_driver_lookup_applicable", return_value=False), \
             mock.patch.object(hw, "nvidia_driver_lookup_applicable", return_value=False):
            failed = veh.session_vendor_failures({})
        assert "amd" not in failed
    finally:
        cache.pop(key, None)


def test_amd_fetch_records_empty_extraction_on_parser_miss() -> None:
    vf.clear_session_diagnostics()
    with mock.patch.object(
        dc, "_amd_http_get_robust", return_value=(True, "<html>no versions here</html>")
    ), mock.patch.object(dc, "_amd_version_from_html", return_value=None):
        hit = dc._amd_fetch_from_download_page(
            {"hw_category": "graphics", "device_label": "AMD Radeon"}
        )
    assert hit is None
    assert vf.empty_extraction_details("amd").get("amd")


def test_intel_product_records_empty_extraction_on_parser_miss() -> None:
    vf.clear_session_diagnostics()
    with mock.patch.object(
        dc, "_intel_product_url", return_value="https://intel.example/x"
    ), mock.patch.object(
        dc, "_fetch_intel_page_html", return_value=(True, "<html>shell</html>", "http")
    ), mock.patch.object(
        dc, "_parse_intel_download_html", return_value=("", "", "")
    ), mock.patch.object(dc, "_intel_best_version_from_html", return_value=""):
        hit = dc._intel_fetch_product_page("graphics")
    assert hit is None
    assert vf.empty_extraction_details("intel").get("intel")


if __name__ == "__main__":
    test_record_empty_extraction_tracked()
    test_session_failures_include_empty_extraction()
    test_session_failures_include_coverage_check_failed_rows()
    test_successful_version_suppresses_empty_extraction()
    test_amd_fetch_records_empty_extraction_on_parser_miss()
    test_intel_product_records_empty_extraction_on_parser_miss()
    print("parser-rot detection tests OK")
