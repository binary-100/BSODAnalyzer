"""v6 Batch 6 — extended vendor scrapers (Marvell, Synaptics/Elan, peripherals)."""

from __future__ import annotations

from unittest import mock

import driver_catalog as dc
import product_version as pv

if not pv.is_v6_line():
    print("SKIP (v6 only)")
    raise SystemExit(0)

MARVELL_HTML = """
"title": "Marvell Yukon 88E8056 PCI-E Gigabit Ethernet Driver"
"version": "12.10.17.3"
"title": "Marvell 9230 NVMe RAID Driver"
"version": "4.5.0.1234"
"""


def test_marvell_product_kind_network() -> None:
    assert dc._marvell_product_kind({
        "device_label": "Marvell Yukon 88E8056 PCI-E Gigabit",
        "pnp_class": "net",
        "instance_id": "PCI\\VEN_11AB&DEV_436B",
    }) == "network"


def test_marvell_product_kind_storage() -> None:
    assert dc._marvell_product_kind({
        "device_label": "Marvell NVMe RAID Controller",
        "pnp_class": "scsi",
        "instance_id": "PCI\\VEN_1B4B&DEV_9230",
    }) == "storage"


def test_scrape_marvell_support_versions() -> None:
    with mock.patch.object(dc, "_vendor_http_get_robust", return_value=(True, MARVELL_HTML)):
        rows = dc._scrape_marvell_support_versions("network")
    assert any(r.get("version") == "12.10.17.3" for r in rows)


def test_peripheral_model_hint_tplink() -> None:
    assert dc._peripheral_model_hint("TP-Link Archer T3U Plus") == "Archer T3U"


def test_peripheral_support_url_logitech() -> None:
    url, title = dc._peripheral_support_url("logitech", "Logitech G502 HERO")
    assert "logi.com" in url
    assert "G502" in title


def test_fetch_synaptics_touchpad() -> None:
    offers = dc.fetch_synaptics_driver_offers({
        "vendor_key": "synaptics",
        "device_label": "Synaptics SMBus ClickPad",
        "pnp_class": "mouse",
    })
    assert "ClickPad" in offers[0]["title"]
    assert offers[0]["confidence"] == "low"


def test_fetch_elan_touchpad() -> None:
    offers = dc.fetch_elan_driver_offers({
        "vendor_key": "elan",
        "device_label": "ELAN SMBus Touchpad",
    })
    assert "ELAN" in offers[0]["title"]


def test_extended_vendor_dispatch_marvell() -> None:
    ctx = {
        "vendor_key": "marvell",
        "device_label": "Marvell Yukon 88E8056",
        "pnp_class": "net",
    }
    with (
        mock.patch("driver_catalog._vendor_scrape_cache_get", return_value=None),
        mock.patch(
            "driver_catalog.fetch_marvell_driver_offers",
            return_value=[{"title": "Marvell pkg", "version": "1.0"}],
        ),
        mock.patch("driver_catalog._vendor_scrape_cache_set"),
    ):
        out = dc.fetch_extended_vendor_offers(ctx)
    assert out[0]["title"] == "Marvell pkg"


def test_amd_gpu_family_hint() -> None:
    assert dc._amd_gpu_family_hint({
        "device_label": "AMD Radeon RX 7800 XT",
    }) == "RX 7800 XT"


def test_version_near_product_in_html() -> None:
    html = "RX 7800 XT section driver package 32.0.15.6094 release"
    assert dc._version_near_product_in_html(html, "RX 7800 XT") == "32.0.15.6094"


def test_intel_dsa_utility_offer() -> None:
    row = dc._intel_dsa_utility_offer({"instance_id": "PCI\\VEN_8086"}, scraped_version="")
    assert row["source"] == "utility"
    assert "Support Assistant" in row["title"]
    assert "intel.com" in row["url"]


def test_fetch_intel_includes_dsa_v6() -> None:
    ctx = {
        "vendor_key": "intel",
        "pnp_class": "display",
        "hw_category": "gpu",
        "device_label": "Intel(R) UHD Graphics 630",
        "instance_id": "PCI\\VEN_8086&DEV_3E92",
    }
    with mock.patch("driver_catalog._vendor_scrape_cache_get", return_value=("1.2.3", "2025-01-01", "http://x", "")):
        offers = dc.fetch_intel_driver_offers(ctx)
    assert len(offers) == 2
    assert offers[1]["source_label"] == "Intel DSA"


def test_v5_skips_extended_vendors() -> None:
    with mock.patch.object(dc, "_v6_catalog_enabled", return_value=False):
        assert dc.fetch_extended_vendor_offers({"vendor_key": "marvell"}) == []


if __name__ == "__main__":
    test_marvell_product_kind_network()
    test_marvell_product_kind_storage()
    test_scrape_marvell_support_versions()
    test_peripheral_model_hint_tplink()
    test_peripheral_support_url_logitech()
    test_fetch_synaptics_touchpad()
    test_fetch_elan_touchpad()
    test_extended_vendor_dispatch_marvell()
    test_amd_gpu_family_hint()
    test_version_near_product_in_html()
    test_intel_dsa_utility_offer()
    test_fetch_intel_includes_dsa_v6()
    test_v5_skips_extended_vendors()
    print("Extended vendor scraper tests OK")
