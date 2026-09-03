"""v6 Batch 3 — network vendor scrapers (Killer, Broadcom, Qualcomm, MediaTek)."""

from __future__ import annotations

from unittest import mock

import driver_catalog as dc
import product_version as pv

if not pv.is_v6_line():
    print("SKIP (v6 only)")
    raise SystemExit(0)

KILLER_HTML = """
Version
40.26.403.2234 (Latest) 40.26.220.2126
Date 4/28/2026
Download KillerPerformanceSuite_40.26.403.2234_UWD_x64.exe
24.40.0.4 for Intel Killer Wi-Fi BE1750, AX1690
10.79.50.1003 (Windows 10 x64), 1168.28.50.1224 (Windows 11) for Intel Killer Ethernet E2500v2, E2600
"""

MT7630_HTML = """
<a href="https://d86o2zu8ugzlg.cloudfront.net/mediatek-craft/drivers/IS_RT2860_W7-5.0.55.0_W8-5.0.55.0_W8Blue-5.0.55.0_20150225_5.0.55.0_Free.zip">download</a>
"""


def test_parse_intel_download_html_latest() -> None:
    ver, date_s, installer = dc._parse_intel_download_html(KILLER_HTML)
    assert ver == "40.26.403.2234"
    assert date_s == "2026-04-28"
    assert "KillerPerformanceSuite" in installer


def test_killer_component_version_wifi() -> None:
    ver = dc._killer_component_version(KILLER_HTML, "Intel Killer Wi-Fi 6E AX1690")
    assert ver == "24.40.0.4"


def test_killer_component_version_ethernet() -> None:
    ver = dc._killer_component_version(KILLER_HTML, "Killer E2600 Ethernet")
    assert ver in ("1168.28.50.1224", "10.79.50.1003")


def test_fetch_killer_offers_uses_component_version() -> None:
    ctx = {
        "vendor_key": "killer",
        "device_label": "Intel Killer Wi-Fi 6E AX1690",
        "pnp_class": "net",
    }
    with mock.patch.object(dc, "_vendor_http_get_robust", return_value=(True, KILLER_HTML)):
        offers = dc.fetch_killer_driver_offers(ctx)
    assert offers[0]["version"] == "24.40.0.4"
    assert offers[0]["confidence"] == "medium"


def test_qualcomm_chip_hint() -> None:
    assert dc._qualcomm_chip_hint({
        "device_label": "Qualcomm QCA6174A 802.11ac Wireless",
    }) == "QCA6174A"


def test_fetch_qualcomm_offers_chip_title() -> None:
    offers = dc.fetch_qualcomm_driver_offers({
        "vendor_key": "qualcomm",
        "device_label": "Qualcomm QCA6174A Wireless",
        "pnp_class": "net",
    })
    assert "QCA6174A" in offers[0]["title"]
    assert offers[0]["version"] == ""


def test_mediatek_slug_from_devid() -> None:
    assert dc._mediatek_product_slug({
        "instance_id": "PCI\\VEN_14C3&DEV_7961",
        "device_label": "MediaTek Wi-Fi 6",
    }) == "mt7921"


def test_scrape_mediatek_product_rows() -> None:
    with mock.patch("driver_catalog._http_get", return_value=(True, MT7630_HTML)):
        rows = dc._scrape_mediatek_product_rows("mt7630")
    assert len(rows) == 1
    assert rows[0]["version"] == "5.0.55.0"


def test_fetch_mediatek_legacy_zip() -> None:
    ctx = {
        "vendor_key": "mediatek",
        "device_label": "MediaTek MT7630",
        "instance_id": "PCI\\VEN_14C3&DEV_7630",
        "pnp_class": "net",
    }
    with mock.patch("driver_catalog._http_get", return_value=(True, MT7630_HTML)):
        offers = dc.fetch_mediatek_driver_offers(ctx)
    assert offers[0]["version"] == "5.0.55.0"
    assert "cloudfront" in offers[0]["url"]


def test_mediatek_mscatalog_queries() -> None:
    ctx = {
        "device_label": "MediaTek Wi-Fi 6 MT7921 Wireless LAN Card",
        "pnp_class": "Net",
        "vendor_key": "mediatek",
    }
    qs = dc._mediatek_mscatalog_queries(ctx)
    assert "MediaTek, Inc. Driver Update" in qs
    assert any("MT7921" in q for q in qs)


def test_fetch_broadcom_guidance() -> None:
    offers = dc.fetch_broadcom_driver_offers({
        "vendor_key": "broadcom",
        "device_label": "Broadcom NetXtreme Gigabit Ethernet",
        "pnp_class": "net",
    })
    assert "Broadcom" in offers[0]["title"]
    assert "Catalog" in offers[0]["notes"]


def test_network_vendor_dispatch() -> None:
    with (
        mock.patch("driver_catalog._vendor_scrape_cache_get", return_value=None),
        mock.patch("driver_catalog.fetch_killer_driver_offers", return_value=[{"title": "k"}]),
        mock.patch("driver_catalog._vendor_scrape_cache_set"),
    ):
        out = dc.fetch_network_vendor_offers({"vendor_key": "killer"})
    assert out[0]["title"] == "k"


def test_v5_skips_network_vendors() -> None:
    with mock.patch.object(dc, "_v6_catalog_enabled", return_value=False):
        assert dc.fetch_network_vendor_offers({"vendor_key": "killer"}) == []


if __name__ == "__main__":
    test_parse_intel_download_html_latest()
    test_killer_component_version_wifi()
    test_killer_component_version_ethernet()
    test_fetch_killer_offers_uses_component_version()
    test_qualcomm_chip_hint()
    test_fetch_qualcomm_offers_chip_title()
    test_mediatek_slug_from_devid()
    test_mediatek_mscatalog_queries()
    test_scrape_mediatek_product_rows()
    test_fetch_mediatek_legacy_zip()
    test_fetch_broadcom_guidance()
    test_network_vendor_dispatch()
    test_v5_skips_network_vendors()
    print("Network vendor scraper tests OK")
