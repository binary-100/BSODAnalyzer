"""Parity: bundled extractor rules match the historical hardcoded parser results.

These fixtures freeze the pre-migration scraper outputs so a rule migration
cannot silently change what versions the tool reports.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import driver_catalog as dc
import vendor_extractors as vex


# ---------------------------------------------------------------------------
# Fixtures (frozen expected outcomes from the pre-migration parsers)
# ---------------------------------------------------------------------------
INTEL_LATEST_HTML = """
Version
40.26.403.2234 (Latest) 40.26.220.2126
Date 4/28/2026
Download KillerPerformanceSuite_40.26.403.2234_UWD_x64.exe
"""

INTEL_EMBEDDED_HTML = """
<html><script id="__NEXT_DATA__" type="application/json">
{"props":{"pageProps":{"downloads":[
{"driverVersion":"31.0.101.1000"},
{"fileVersion":"32.0.101.6790"}
]}}}
</script></html>
"""

AMD_GRAPHICS_HTML = (
    '<html><script id="__NEXT_DATA__" type="application/json">'
    '{"props":{"pageProps":{"version":"26.6.4",'
    '"driverPackageVersion":"32.0.21043.19003"}}}'
    "</script>"
    "AMD Software: Adrenalin Edition 26.5.1</html>"
)

AMD_CHIPSET_HTML = (
    'chipset drivers package 6.05.28.016 and ryzen chipset 5.08.02.027 '
    'also see 7.12.30.210'
)

GIGABYTE_HTML = (
    '{"fileTitle":"AMD Chipset Drivers","fileVersion":"6.02.22.027"}'
    '{"fileTitle":"Realtek LAN\\/Ethernet","fileVersion":"10.73.822.2025"}'
    "/FileList/Driver/mb_driver_123_realtek_1.2.3.4.zip"
)

MARVELL_HTML = """
"title": "Marvell Yukon 88E8056 PCI-E Gigabit Ethernet Driver"
"version": "12.10.17.3"
"title": "Marvell 9230 NVMe RAID Driver"
"version": "4.5.0.1234"
"""

MEDIATEK_HTML = """
<a href="https://d86o2zu8ugzlg.cloudfront.net/mediatek-craft/drivers/IS_RT2860_W7-5.0.55.0_W8-5.0.55.0_W8Blue-5.0.55.0_20150225_5.0.55.0_Free.zip">download</a>
<a href="https://cdn.example.com/unrelated/app_9.9.9.exe">skip</a>
"""


# ---------------------------------------------------------------------------
# Bundled rules exist for HTML scrapers (API vendors intentionally absent)
# ---------------------------------------------------------------------------
def test_bundled_extractors_cover_html_vendors() -> None:
    for vendor in ("amd", "intel", "gigabyte", "marvell", "mediatek"):
        assert vendor in vex.BUNDLED_EXTRACTORS, vendor
    # API-driven — not HTML extractors
    assert "realtek" not in vex.BUNDLED_EXTRACTORS
    assert "nvidia" not in vex.BUNDLED_EXTRACTORS


# ---------------------------------------------------------------------------
# Intel / Killer download-detail parity
# ---------------------------------------------------------------------------
def test_intel_latest_parity() -> None:
    ver, date_s, installer = dc._parse_intel_download_html(INTEL_LATEST_HTML)
    assert ver == "40.26.403.2234"
    assert date_s == "2026-04-28"
    assert "KillerPerformanceSuite" in installer
    # Engine alone agrees on version
    assert vex.extract_bundled_version("intel", INTEL_LATEST_HTML, hint="graphics") == (
        "40.26.403.2234"
    )


def test_intel_embedded_json_parity() -> None:
    ver = dc._parse_intel_version_from_embedded_json(INTEL_EMBEDDED_HTML, hint="graphics")
    assert ver == "32.0.101.6790"
    assert vex.extract_bundled_version("intel", INTEL_EMBEDDED_HTML, hint="graphics") == (
        "32.0.101.6790"
    )


# ---------------------------------------------------------------------------
# AMD parity
# ---------------------------------------------------------------------------
def test_amd_graphics_parity() -> None:
    # Historical: __NEXT_DATA__ 4-part max → 32.0.21043.19003
    assert dc._parse_amd_page_version(AMD_GRAPHICS_HTML) == "32.0.21043.19003"
    assert vex.extract_bundled_version("amd", AMD_GRAPHICS_HTML, hint="graphics") == (
        "32.0.21043.19003"
    )


def test_amd_chipset_parity() -> None:
    hit = dc._amd_version_from_html(
        AMD_CHIPSET_HTML, {"hw_category": "chipset", "device_label": "AMD SMBus"}
    )
    assert hit is not None
    # Historical findall + max on chipset[^"]{0,160}(4-part) is greedy within the
    # window, so the highest 4-part version near "chipset" wins.
    assert hit[0] == "7.12.30.210"
    assert vex.extract_bundled_version("amd", AMD_CHIPSET_HTML, hint="chipset") == (
        "7.12.30.210"
    )


# ---------------------------------------------------------------------------
# Gigabyte / Marvell / MediaTek row parity
# ---------------------------------------------------------------------------
def test_gigabyte_rows_parity() -> None:
    rows = dc._parse_gigabyte_support_html(GIGABYTE_HTML, "https://gigabyte.example/support")
    vers = {r["version"] for r in rows}
    titles = {r["title"] for r in rows}
    assert "6.02.22.027" in vers
    assert "10.73.822.2025" in vers
    assert "Realtek LAN/Ethernet" in titles
    # FileList secondary path still attached by code
    assert any("1.2.3.4" == r.get("version") for r in rows)


def test_marvell_network_parity() -> None:
    from unittest import mock

    with mock.patch.object(dc, "_vendor_http_get_robust", return_value=(True, MARVELL_HTML)):
        rows = dc._scrape_marvell_support_versions("network")
    assert any(r.get("version") == "12.10.17.3" for r in rows)
    # Storage-only NVMe RAID must not leak into network kind
    assert not any(r.get("version") == "4.5.0.1234" for r in rows)


def test_marvell_storage_parity() -> None:
    from unittest import mock

    with mock.patch.object(dc, "_vendor_http_get_robust", return_value=(True, MARVELL_HTML)):
        rows = dc._scrape_marvell_support_versions("storage")
    assert any(r.get("version") == "4.5.0.1234" for r in rows)


def test_mediatek_rows_parity() -> None:
    from unittest import mock

    with mock.patch.object(dc, "_http_get", return_value=(True, MEDIATEK_HTML)):
        rows = dc._scrape_mediatek_product_rows("mt7630")
    assert len(rows) == 1
    assert rows[0]["version"] == "5.0.55.0"
    assert "cloudfront" in rows[0]["url"]


if __name__ == "__main__":
    test_bundled_extractors_cover_html_vendors()
    test_intel_latest_parity()
    test_intel_embedded_json_parity()
    test_amd_graphics_parity()
    test_amd_chipset_parity()
    test_gigabyte_rows_parity()
    test_marvell_network_parity()
    test_marvell_storage_parity()
    test_mediatek_rows_parity()
    print("extractor parity tests OK")
