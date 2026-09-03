"""v6 Batch 4 — OEM depth (D19–D21): API parity, source conflicts, cache freshness."""

from __future__ import annotations

import json
from unittest import mock

import driver_catalog as dc


HP_WCC_DRIVER_JSON = {
    "data": {
        "softwareTypes": [{
            "accordionName": "Driver-Audio",
            "softwareDriversList": [{
                "latestVersionDriver": {
                    "title": "Realtek High Definition Audio Driver",
                    "version": "6.0.9700.1",
                    "versionUpdatedDateString": "2025-03-01",
                    "fileUrl": "https://ftp.hp.com/pub/softpaq/sp123456.exe",
                },
            }],
        }],
    },
}

HP_OS_JSON = {
    "data": {
        "osAvailablePlatformsAnsOS": {
            "osPlatforms": [{
                "osName": "Windows",
                "osVersions": [{
                    "name": "Microsoft Windows 11 64-bit",
                    "id": "11111111111111111111111111111111111111111111",
                }],
            }],
        },
    },
}

HP_SPECS_JSON = {
    "devices": [{
        "productSpecs": {
            "data": {
                "productLineCode": "6U",
                "productNumberOid": 12345,
                "productSeriesOid": 67890,
            },
        },
    }],
}

HP_TYPEAHEAD_JSON = {
    "matches": [{
        "pmClass": "pm_series_value",
        "productId": "67890",
        "name": "HP EliteBook 840 G10",
    }],
}


def test_oem_model_slug_variants() -> None:
    variants = dc._oem_model_slug_variants("ROG STRIX B550-F GAMING")
    assert "ROG STRIX B550-F GAMING" in variants
    assert any("STRIX" in v for v in variants)
    assert any("-" in v for v in variants)


def test_gigabyte_support_urls_include_laptop() -> None:
    ctx = {"system_model": "AORUS 15G Laptop", "baseboard_product": ""}
    urls = dc._gigabyte_support_page_urls("AORUS-15G", ctx)
    assert any("/Laptop/" in u for u in urls)
    assert any("/AORUS/" in u for u in urls)


def test_parse_hp_wcc_driver_details() -> None:
    rows = dc._parse_hp_wcc_driver_details(HP_WCC_DRIVER_JSON)
    assert len(rows) == 1
    assert rows[0]["version"] == "6.0.9700.1"
    assert rows[0]["category"] == "Driver-Audio"


def test_hp_fetch_wcc_driver_rows_mocked() -> None:
    system = {"system_manufacturer": "HP", "system_model": "EliteBook 840 G10"}

    def fake_get(url, headers=None, referer=None, insecure_fallback=False):
        if "typeahead" in url:
            return True, json.dumps(HP_TYPEAHEAD_JSON)
        if "osVersionData" in url:
            return True, json.dumps(HP_OS_JSON)
        return False, ""

    def fake_post(url, payload, headers=None, referer=None):
        if "warranty/specs" in url:
            return True, json.dumps(HP_SPECS_JSON)
        if "driverDetails" in url:
            return True, json.dumps(HP_WCC_DRIVER_JSON)
        return False, ""

    with mock.patch.object(dc, "_http_get", side_effect=fake_get):
        with mock.patch.object(dc, "_http_post_json", side_effect=fake_post):
            rows = dc._hp_fetch_wcc_driver_rows(system)
    assert rows and rows[0]["version"] == "6.0.9700.1"


def test_get_hp_oem_rows_falls_back_to_wcc() -> None:
    system = {"system_manufacturer": "HP Inc.", "system_model": "EliteBook 840 G10"}

    with mock.patch.object(
        dc,
        "_http_get",
        return_value=(False, ""),
    ):
        with mock.patch.object(
            dc,
            "_hp_fetch_wcc_driver_rows",
            return_value=[{
                "title": "Intel Wi-Fi Driver",
                "version": "23.120.0",
                "date": "2025-01-01",
                "url": "https://ftp.hp.com/example.exe",
                "category": "Driver-Network",
            }],
        ):
            with mock.patch.object(
                dc,
                "_merge_enterprise_oem_rows",
                side_effect=lambda rows, _ctx, _vendor: rows,
            ):
                rows, fallback = dc.get_hp_oem_rows(system)
    assert len(rows) == 1
    assert rows[0]["version"] == "23.120.0"
    assert "support.hp.com" in fallback


def test_annotate_offer_source_conflicts() -> None:
    offers = dc.enrich_offers_with_comparison(
        [
            {
                "source": "oem",
                "source_label": "OEM (HP)",
                "title": "Realtek Audio",
                "version": "6.0.9700.1",
            },
            {
                "source": "microsoft",
                "source_label": "Microsoft (Windows driver catalog)",
                "title": "Realtek Audio",
                "version": "6.0.9126.1",
            },
        ],
        "6.0.9000.0",
    )
    out = dc.annotate_offer_source_conflicts(offers)
    assert all(o.get("source_conflict") for o in out)
    summary = dc.offer_source_conflict_summary(out)
    assert "Source conflict" in summary
    assert "6.0.9700.1" in summary
    assert "6.0.9126.1" in summary


def test_no_conflict_when_versions_match() -> None:
    offers = dc.enrich_offers_with_comparison(
        [
            {"source": "oem", "title": "Audio", "version": "6.0.9126.1"},
            {"source": "microsoft", "title": "Audio", "version": "6.0.9126.1"},
        ],
        "6.0.9000.0",
    )
    out = dc.annotate_offer_source_conflicts(offers)
    assert not any(o.get("source_conflict") for o in out)
    assert dc.offer_source_conflict_summary(out) == ""


def test_oem_data_freshness_note() -> None:
    assert "Live OEM" in dc.oem_data_freshness_note("live")
    assert "Stale" in dc.oem_data_freshness_note("stale_disk")


def test_tag_offer_freshness() -> None:
    tagged = dc._tag_offer_freshness([{"source": "oem", "title": "x"}], "session")
    assert tagged[0]["data_freshness"] == "session"


def test_oem_session_cache_tags_freshness() -> None:
    dc.clear_oem_cache()
    dc.configure_catalog(oem_session_cache=True)
    calls = {"n": 0}

    def fetch_rows(_sys):
        calls["n"] += 1
        return ([{"title": "pkg", "version": "1.0", "url": "https://example.test"}], "https://hp.com")

    first_rows, _ = dc._cached_oem_rows("hp", fetch_rows, {"system_manufacturer": "HP", "system_model": "test"})
    second_rows, _ = dc._cached_oem_rows("hp", fetch_rows, {"system_manufacturer": "HP", "system_model": "test"})
    assert calls["n"] == 1
    assert first_rows[0]["version"] == "1.0"
    assert second_rows[0]["version"] == "1.0"


if __name__ == "__main__":
    test_oem_model_slug_variants()
    test_gigabyte_support_urls_include_laptop()
    test_parse_hp_wcc_driver_details()
    test_hp_fetch_wcc_driver_rows_mocked()
    test_get_hp_oem_rows_falls_back_to_wcc()
    test_annotate_offer_source_conflicts()
    test_no_conflict_when_versions_match()
    test_oem_data_freshness_note()
    test_tag_offer_freshness()
    test_oem_session_cache_tags_freshness()
    print("OEM depth batch 4 tests OK")
