"""Peripheral firmware vendor registry — multi-vendor support site search."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import firmware_peripheral_vendors as fpv

_FIXTURES = Path(__file__).resolve().parent / "fixtures"


def test_usb_product_hint_pro_type_ultra_pid() -> None:
    hint = fpv.product_hint(r"HID\VID_1532&PID_0277&MI_00\9&2CE64270&0&0000")
    assert hint is not None
    assert hint.product_name == "Razer Pro Type Ultra"
    assert "6217" in hint.firmware_article_ids


def test_usb_product_hint_mx_keys_article_id() -> None:
    hint = fpv.product_hint(r"HID\VID_046D&PID_408A&MI_00\8&252A5CF&0&0000")
    assert hint is not None
    assert hint.product_name == "Logitech MX Keys"
    assert "14648663676183" in hint.firmware_article_ids


def test_usb_product_hint_g900_pid() -> None:
    hint = fpv.product_hint(r"HID\VID_046D&PID_C081&MI_01\8&252A5CF&0&0000")
    assert hint is not None
    assert "G900" in hint.product_name
    assert "MX Keys" not in hint.product_name


def test_parse_mx_keys_release_notes_table() -> None:
    html = (
        Path(__file__).resolve().parent
        / "fixtures"
        / "logitech_mx_keys_firmware_release_notes.html"
    ).read_text(encoding="utf-8")
    row = fpv.parse_zendesk_article(
        html,
        article_url="https://support.logi.com/hc/en-001/articles/14648663676183",
        title_hint="MX Keys Firmware Release Notes",
    )
    assert row is not None
    assert row.version == "12.01.13"


def test_fetch_logitech_mx_keys_known_article() -> None:
    article = (
        Path(__file__).resolve().parent
        / "fixtures"
        / "logitech_mx_keys_firmware_release_notes.html"
    ).read_text(encoding="utf-8")
    ctx = {
        "device_id": r"HID\VID_046D&PID_408A&MI_01\8&252A5CF&0&0001",
        "device_label": "Logitech MX Keys",
        "subcategory": "keyboard",
    }
    url = "https://support.logi.com/hc/en-001/articles/14648663676183"
    cache = {f"article:{fpv._cache_key(url)}": article}
    cache[f"article:{fpv._cache_key('https://support.logi.com/hc/en-us/articles/14648663676183')}"] = article
    row = fpv.fetch_vendor_peripheral_firmware("logitech", ctx, html_cache=cache)
    assert row is not None
    assert row["version"] == "12.01.13"
    assert row.get("product_name") == "Logitech MX Keys"


def test_peripheral_offer_driver_version_is_uncertain() -> None:
    row = {
        "title": "Razer Pro Type Ultra Firmware Updater",
        "version": "1.03.00_r3",
        "url": "https://mysupport.razer.com/app/answers/detail/a_id/6217",
        "notes": "Standalone updater",
        "installed_source": "driver_version",
    }
    offer = fpv.peripheral_offer_from_row(row, installed="1.3.0.0")
    assert offer["vs_installed"] == "uncertain"


def test_parse_razer_firmware_article_snippet() -> None:
    html = (_FIXTURES / "razer_pro_type_ultra_firmware_article_snippet.html").read_text(encoding="utf-8")
    row = fpv.parse_razer_article(html, article_url="https://mysupport.razer.com/app/answers/detail/a_id/6217")
    assert row is not None
    assert row.version == "1.03.00_r3"
    assert row.sku == "RZ03-04110"


def test_search_razer_firmware_articles_snippet() -> None:
    html = (_FIXTURES / "razer_support_search_snippet.html").read_text(encoding="utf-8")
    hits = fpv.search_razer_articles("Pro Type Ultra firmware", html)
    assert hits
    assert hits[0][0] == "6217"
    assert "Firmware Updater" in hits[0][1]


def test_fetch_razer_peripheral_firmware_with_fixture_cache() -> None:
    article = (_FIXTURES / "razer_pro_type_ultra_firmware_article_snippet.html").read_text(encoding="utf-8")
    ctx = {
        "device_id": r"HID\VID_1532&PID_0277&MI_00\9&2CE64270&0&0000",
        "device_label": "HID Keyboard Device",
        "subcategory": "keyboard",
    }
    cache = {f"article:{fpv._cache_key('https://mysupport.razer.com/app/answers/detail/a_id/6217')}": article}
    row = fpv.fetch_vendor_peripheral_firmware("razer", ctx, html_cache=cache)
    assert row is not None
    assert row["version"] == "1.03.00_r3"


def test_zendesk_search_and_parse_logitech_g810() -> None:
    search_json = json.loads((_FIXTURES / "logitech_zendesk_search_g810.json").read_text(encoding="utf-8"))
    article = (_FIXTURES / "logitech_g810_firmware_article_snippet.html").read_text(encoding="utf-8")

    def fake_zendesk(
        base: str,
        query: str,
        locale_path: str = "/hc/en-us",
        *,
        cache=None,
    ) -> list[dict]:
        assert "logi.com" in base
        return search_json["results"]

    ctx = {
        "device_id": r"HID\VID_046D&PID_C232\2&357F35A&0&0000",
        "device_label": "Logitech G810 Orion Spectrum",
        "subcategory": "keyboard",
    }
    article_url = search_json["results"][0]["html_url"]
    cache = {f"article:{fpv._cache_key(article_url)}": article}

    with patch.object(fpv, "search_zendesk_articles", side_effect=fake_zendesk):
        row = fpv.fetch_vendor_peripheral_firmware("logitech", ctx, html_cache=cache)
    assert row is not None
    assert row["version"] == "102.1.22"
    assert row["parse_method"] == "zendesk_support_article"


def test_build_search_queries_includes_product_and_class() -> None:
    cfg = fpv.VENDOR_SITE_REGISTRY["logitech"]
    ctx = {
        "device_label": "Logitech G810 Orion Spectrum",
        "subcategory": "keyboard",
    }
    queries = fpv.build_search_queries(ctx, cfg)
    assert any("G810" in q or "g810" in q.lower() for q in queries)
    assert any("keyboard" in q.lower() for q in queries)


def test_peripheral_offer_hid_driver_not_compared() -> None:
    row = {
        "title": "Razer Pro Type Ultra Firmware Updater",
        "version": "1.03.00_r3",
        "url": "https://mysupport.razer.com/app/answers/detail/a_id/6217",
        "notes": "Standalone updater",
    }
    offer = fpv.peripheral_offer_from_row(row, installed="10.0.26100.8521")
    assert offer["vs_installed"] == "catalog_only"
    assert offer["source_label"] == "Vendor support site"


def test_vendor_registry_covers_major_peripheral_vendors() -> None:
    for vk in ("razer", "logitech", "corsair", "steelseries", "elgato", "hyperx"):
        assert vk in fpv.VENDOR_SITE_REGISTRY


if __name__ == "__main__":
    test_usb_product_hint_pro_type_ultra_pid()
    test_parse_razer_firmware_article_snippet()
    test_search_razer_firmware_articles_snippet()
    test_fetch_razer_peripheral_firmware_with_fixture_cache()
    test_zendesk_search_and_parse_logitech_g810()
    test_usb_product_hint_mx_keys_article_id()
    test_usb_product_hint_g900_pid()
    test_parse_mx_keys_release_notes_table()
    test_fetch_logitech_mx_keys_known_article()
    test_peripheral_offer_driver_version_is_uncertain()
    test_build_search_queries_includes_product_and_class()
    test_peripheral_offer_hid_driver_not_compared()
    test_vendor_registry_covers_major_peripheral_vendors()
    print("ok")
