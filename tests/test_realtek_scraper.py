"""v6 Batch 2 — Realtek download-center scraper (mocked, no network)."""

from __future__ import annotations

import json
from unittest import mock

import driver_catalog as dc
import product_version as pv

if not pv.is_v6_line():
    print("SKIP (v6 only)")
    raise SystemExit(0)

SAMPLE_PAYLOAD = {
    "Pass": True,
    "Data": {
        "Id": "593",
        "Title": "PC Audio Codecs > High Definition Audio Codecs  Software",
        "DownloadItems": {
            "Windows": [
                {
                    "DownloadId": "4001",
                    "Name": "Install_Win11_9782.zip",
                    "Description": "Win11 Auto Installation Program",
                    "OSName": "Windows",
                    "Version": "6.0.9782.1",
                    "UpdateTime": "2026/04/27",
                    "DownloadUrl": "/Download/ToDownload?type=direct&downloadid=4001",
                },
                {
                    "DownloadId": "4002",
                    "Name": "Diagnostic_v2.zip",
                    "Description": "Ethernet Diagnostic Program",
                    "OSName": "Windows",
                    "Version": "2.0.8.1",
                    "UpdateTime": "2024/09/25",
                    "DownloadUrl": "/Download/ToDownload?type=direct&downloadid=4002",
                },
            ],
        },
    },
}


def test_realtek_cate_mapping_audio() -> None:
    cate, hint = dc._realtek_cate_id_for_ctx({
        "device_label": "Realtek(R) Audio",
        "pnp_class": "media",
        "vendor_key": "realtek",
    })
    assert cate == "593"
    assert hint == "audio"


def test_realtek_cate_mapping_pcie_nic_by_devid() -> None:
    cate, hint = dc._realtek_cate_id_for_ctx({
        "device_label": "Realtek PCIe GbE Family Controller",
        "pnp_class": "net",
        "instance_id": "PCI\\VEN_10EC&DEV_8168&SUBSYS_01234567&REV_15",
        "vendor_key": "realtek",
    })
    assert cate == "584"
    assert hint == "pci_dev_8168"


def test_realtek_cate_wifi_returns_none() -> None:
    cate, hint = dc._realtek_cate_id_for_ctx({
        "device_label": "Realtek 8822CE Wireless LAN WiFi 6",
        "pnp_class": "net",
        "vendor_key": "realtek",
    })
    assert cate is None
    assert hint == "wifi_oem"


def test_realtek_rows_from_api_payload() -> None:
    rows = dc._realtek_rows_from_api_payload(SAMPLE_PAYLOAD)
    assert len(rows) == 2
    assert rows[0]["version"] == "6.0.9782.1"
    assert rows[0]["url"].startswith("https://www.realtek.com/Download/")


def test_fetch_realtek_driver_offers_picks_driver_not_diagnostic() -> None:
    ctx = {
        "vendor_key": "realtek",
        "device_label": "Realtek(R) Audio",
        "pnp_class": "media",
    }
    with mock.patch(
        "driver_catalog._scrape_realtek_category_rows",
        return_value=dc._realtek_rows_from_api_payload(SAMPLE_PAYLOAD),
    ):
        offers = dc.fetch_realtek_driver_offers(ctx)
    assert len(offers) == 1
    assert offers[0]["version"] == "6.0.9782.1"
    assert "9782" in offers[0]["title"]
    assert offers[0]["confidence"] == "medium"


def test_fetch_realtek_wifi_fallback_link_only() -> None:
    offers = dc.fetch_realtek_driver_offers({
        "vendor_key": "realtek",
        "device_label": "Realtek RTL8852AE Wi-Fi 6",
        "pnp_class": "net",
    })
    assert len(offers) == 1
    assert offers[0]["version"] == ""
    assert "OEM" in offers[0]["notes"]


def test_realtek_legacy_audio_version_not_trusted() -> None:
    assert not dc._realtek_version_trustworthy("593", "R2.83")
    assert not dc._realtek_version_trustworthy("593", "0.1")
    assert dc._realtek_version_trustworthy("593", "6.0.9929.1")
    assert dc._realtek_version_trustworthy("584", "11.029.50")


def test_fetch_realtek_audio_legacy_returns_link_without_version() -> None:
    ctx = {
        "vendor_key": "realtek",
        "device_label": "Realtek(R) Audio",
        "pnp_class": "media",
    }
    legacy_rows = [{
        "title": "HD Audio",
        "package_name": "R2.83 Win10_R283.zip",
        "description": "Win10",
        "version": "R2.83",
        "date": "2020-01-01",
        "url": "https://www.realtek.com/Download/ToDownload?type=direct&downloadid=1",
    }]
    with mock.patch("driver_catalog._scrape_realtek_category_rows", return_value=legacy_rows):
        offers = dc.fetch_realtek_driver_offers(ctx)
    assert offers[0]["version"] == ""
    assert "Microsoft Update Catalog" in offers[0]["notes"]


def test_v5_line_skips_realtek_scraper() -> None:
    with mock.patch.object(dc, "_v6_catalog_enabled", return_value=False):
        offers = dc.fetch_realtek_driver_offers({
            "vendor_key": "realtek",
            "device_label": "Realtek(R) Audio",
            "pnp_class": "media",
        })
    assert offers == []


def test_realtek_device_component_role_wdm() -> None:
    ctx = {
        "vendor_key": "realtek",
        "device_label": "Realtek(R) Audio",
        "pnp_class": "media",
    }
    assert dc._realtek_device_component_role(ctx) == "wdm"


def test_realtek_device_component_role_net() -> None:
    ctx = {
        "vendor_key": "realtek",
        "device_label": "Realtek Gaming 2.5GbE Family Controller",
        "pnp_class": "net",
    }
    assert dc._realtek_device_component_role(ctx) == "net"


def test_realtek_uad_catalog_queries_include_media_years() -> None:
    ctx = {
        "vendor_key": "realtek",
        "device_label": "Realtek(R) Audio",
        "pnp_class": "media",
    }
    queries = dc._realtek_uad_catalog_queries(ctx)
    assert any("Realtek Media" in q for q in queries)
    assert "Realtek sound 22H2" in queries
    assert "Realtek High Definition Audio Driver" in queries


def test_realtek_reject_apo_on_wdm_without_hwid() -> None:
    ctx = {
        "vendor_key": "realtek",
        "device_label": "Realtek(R) Audio",
        "pnp_class": "media",
        "instance_id": "HDAUDIO\\FUNC_01&VEN_10EC&DEV_0897",
    }
    apo_row = {
        "title": "Realtek Semiconductor Corp. - AudioProcessingObject - 13.0.6000.1167",
        "version": "13.0.6000.1167",
    }
    wdm_row = {
        "title": "Realtek Semiconductor Corp. - Media - 6.0.9782.1",
        "version": "6.0.9782.1",
    }
    assert dc._reject_realtek_catalog_row(apo_row, ctx) == "realtek_companion_on_wdm_device"
    assert dc._reject_realtek_catalog_row(wdm_row, ctx) is None


def test_realtek_catalog_queries_cap_for_realtek() -> None:
    ctx = {
        "vendor_key": "realtek",
        "device_label": "Realtek(R) Audio",
        "pnp_class": "media",
        "instance_id": "HDAUDIO\\FUNC_01&VEN_10EC&DEV_0897&SUBSYS_10280B5B",
    }
    queries = dc._catalog_search_queries_for_ctx(ctx)
    assert len(queries) <= 10
    assert any("Realtek Media" in q for q in queries)


def test_realtek_wdm_codec_scoring_beats_apo() -> None:
    ctx = {
        "vendor_key": "realtek",
        "device_label": "Realtek(R) Audio",
        "pnp_class": "media",
    }
    wdm = {
        "title": "Realtek Semiconductor Corp. - Media - 6.0.9782.1",
        "version": "6.0.9782.1",
        "classification": "Drivers",
    }
    apo = {
        "title": "Realtek Semiconductor Corp. - AudioProcessingObject - 13.0.6000.1167",
        "version": "13.0.6000.1167",
        "classification": "Drivers",
    }
    wdm_score = dc._score_catalog_row_for_ctx(wdm, ctx, "Realtek Media 2026", hwid_match=False)
    apo_score = dc._score_catalog_row_for_ctx(apo, ctx, "Realtek Media 2026", hwid_match=False)
    assert wdm_score > apo_score


def test_fetch_microsoft_catalog_prefers_wdm_with_hwid() -> None:
    ctx = {
        "vendor_key": "realtek",
        "device_label": "Realtek(R) Audio",
        "pnp_class": "media",
        "instance_id": "HDAUDIO\\FUNC_01&VEN_10EC&DEV_0897",
    }
    apo_row = {
        "title": "Realtek Semiconductor Corp. - AudioProcessingObject - 13.0.6000.1167",
        "version": "13.0.6000.1167",
        "update_id": "apo-id",
        "classification": "Drivers",
    }
    wdm_row = {
        "title": "Realtek Semiconductor Corp. - Media - 6.0.9782.1",
        "version": "6.0.9782.1",
        "update_id": "wdm-id",
        "classification": "Drivers",
        "hwids": ["HDAUDIO\\FUNC_01&VEN_10EC&DEV_0897"],
    }

    def fake_search(query: str, **kwargs):
        return [apo_row, wdm_row], None

    with mock.patch.object(dc, "_v6_catalog_enabled", return_value=True), mock.patch.object(
        dc, "ensure_mscatalog_module_ready", return_value=(True, "x")
    ), mock.patch(
        "catalog_ps_module.search_mscatalog_updates",
        side_effect=fake_search,
    ), mock.patch.object(
        dc, "_catalog_row_hwid_matches_ctx", side_effect=lambda row, _ctx: row is wdm_row
    ):
        offers = dc.fetch_microsoft_catalog_search_offers(ctx, max_results=2)

    assert offers
    assert offers[0]["version"] == "6.0.9782.1"
    assert "Media" in offers[0]["title"]


def test_fetch_realtek_nic_prefers_installed_major_family() -> None:
    ctx = {
        "vendor_key": "realtek",
        "device_label": "Realtek PCIe GBE Family Controller",
        "pnp_class": "net",
        "primary_version": "10.69.1121.2023",
    }
    rows = [
        {
            "package_name": "Win11 Auto Installation Program",
            "description": "Win11",
            "version": "11.030.50",
            "date": "2026-01-01",
            "url": "https://www.realtek.com/Download/ToDownload?type=direct&downloadid=11",
        },
        {
            "package_name": "Win11 Auto Installation Program",
            "description": "Win11",
            "version": "10.080.50.407",
            "date": "2025-06-01",
            "url": "https://www.realtek.com/Download/ToDownload?type=direct&downloadid=10",
        },
    ]
    with mock.patch("driver_catalog._scrape_realtek_category_rows", return_value=rows):
        offers = dc.fetch_realtek_driver_offers(ctx)
    assert offers[0]["version"] == "10.080.50.407"
    assert "10.x" in offers[0]["notes"] or "10." in offers[0]["notes"]


def test_realtek_best_row_uad_over_legacy() -> None:
    ctx = {
        "vendor_key": "realtek",
        "device_label": "Realtek(R) Audio",
        "pnp_class": "media",
        "primary_version": "6.0.9205.1",
    }
    rows = [
        {
            "package_name": "Legacy HDA",
            "description": "Win10",
            "version": "R2.83",
            "date": "2020-01-01",
            "url": "https://example/legacy",
        },
        {
            "package_name": "UAD",
            "description": "Win11",
            "version": "6.0.9929.1",
            "date": "2026-01-01",
            "url": "https://example/uad",
        },
    ]
    best = dc._realtek_best_row_for_ctx(rows, "593", ctx)
    assert best["version"] == "6.0.9929.1"


if __name__ == "__main__":
    test_realtek_cate_mapping_audio()
    test_realtek_cate_mapping_pcie_nic_by_devid()
    test_realtek_cate_wifi_returns_none()
    test_realtek_rows_from_api_payload()
    test_fetch_realtek_driver_offers_picks_driver_not_diagnostic()
    test_fetch_realtek_wifi_fallback_link_only()
    test_realtek_legacy_audio_version_not_trusted()
    test_fetch_realtek_audio_legacy_returns_link_without_version()
    test_v5_line_skips_realtek_scraper()
    test_realtek_device_component_role_wdm()
    test_realtek_device_component_role_net()
    test_realtek_uad_catalog_queries_include_media_years()
    test_realtek_reject_apo_on_wdm_without_hwid()
    test_realtek_catalog_queries_cap_for_realtek()
    test_realtek_wdm_codec_scoring_beats_apo()
    test_fetch_microsoft_catalog_prefers_wdm_with_hwid()
    test_fetch_realtek_nic_prefers_installed_major_family()
    test_realtek_best_row_uad_over_legacy()
    print("Realtek scraper tests OK")
