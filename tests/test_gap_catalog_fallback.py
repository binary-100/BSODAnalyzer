"""Tests for the HWID-verified coverage-gap Microsoft Update Catalog fallback.

The batch scan reduces non-Realtek devices to a single hardware-ID query, which the
catalog title search never matches. This fallback fires a name search for devices
left with zero offers and attaches ONLY hardware-ID-verified catalog matches — so it
fills real gaps without reintroducing low-confidence/false-positive offers.
"""

from __future__ import annotations

import os
import sys
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import driver_catalog as dc


PCI_CTX = {
    "instance_id": "PCI\\VEN_8086&DEV_15F3&SUBSYS_00000000&REV_03",
    "device_label": "Intel I225-V Ethernet",
    "vendor_key": "intel",
    "pnp_class": "net",
    "_batch_driver_check": True,
}


def _verified_offer() -> dict:
    return {
        "source": "microsoft",
        "source_label": "Microsoft (Update Catalog)",
        "title": "Intel - Net - I225-V 2.1.4.8",
        "version": "2.1.4.8",
        "vs_installed": "newer",
        "hwid_matched": True,
        "confidence": "high",
        "notes": "Matched via Microsoft Update Catalog search.",
    }


def _unverified_offer() -> dict:
    o = _verified_offer()
    o["hwid_matched"] = False
    o["confidence"] = "medium"
    return o


def test_gap_name_queries_drop_hwid_and_generic() -> None:
    qs = dc._gap_catalog_name_queries_for_ctx(PCI_CTX)
    assert qs, "expected at least one name query"
    assert all(not dc._is_hwid_query(q) for q in qs), qs
    assert all(q.lower() not in dc._GENERIC_PNP_DEVICE_LABELS for q in qs), qs


def test_gap_name_queries_empty_for_generic_label() -> None:
    ctx = dict(PCI_CTX)
    # A purely generic label with no vendor/name signal should yield no name queries.
    ctx["device_label"] = next(iter(dc._GENERIC_PNP_DEVICE_LABELS))
    ctx["vendor_key"] = ""
    qs = dc._gap_catalog_name_queries_for_ctx(ctx)
    assert all(q.lower() not in dc._GENERIC_PNP_DEVICE_LABELS for q in qs), qs


def test_augment_attaches_verified_offer() -> None:
    results = [{"device_name": "Intel I225-V", "installed_version": "1.0.0.0",
                "offers": [], "status": "none"}]
    contexts = {"Intel I225-V": dict(PCI_CTX)}
    captured: dict = {}

    def fake_fetch(ctx, *, max_results=3):
        captured["ctx"] = ctx
        return [_verified_offer()]

    with mock.patch.object(dc, "_v6_catalog_enabled", return_value=True), \
         mock.patch.object(dc, "is_quick_check_mode", return_value=False), \
         mock.patch.object(dc, "_gui_gap_catalog_fallback_enabled", return_value=True), \
         mock.patch.object(dc, "ensure_mscatalog_module_ready", return_value=(True, "")), \
         mock.patch.object(dc, "_warm_gap_mscatalog_queries"), \
         mock.patch.object(dc, "fetch_microsoft_catalog_search_offers", side_effect=fake_fetch):
        dc._augment_gap_devices_with_verified_catalog(results, contexts, None)

    assert results[0]["offers"], "verified offer should be attached"
    assert results[0]["offers"][0]["hwid_matched"] is True
    assert "coverage-gap check" in results[0]["offers"][0]["notes"].lower()
    # The device is re-searched by NAME, not the collapsed batch HWID query.
    assert "_batch_driver_check" not in captured["ctx"]


def test_augment_rejects_unverified_offer() -> None:
    results = [{"device_name": "Intel I225-V", "installed_version": "1.0.0.0",
                "offers": [], "status": "none"}]
    contexts = {"Intel I225-V": dict(PCI_CTX)}

    with mock.patch.object(dc, "_v6_catalog_enabled", return_value=True), \
         mock.patch.object(dc, "is_quick_check_mode", return_value=False), \
         mock.patch.object(dc, "_gui_gap_catalog_fallback_enabled", return_value=True), \
         mock.patch.object(dc, "ensure_mscatalog_module_ready", return_value=(True, "")), \
         mock.patch.object(dc, "_warm_gap_mscatalog_queries"), \
         mock.patch.object(dc, "fetch_microsoft_catalog_search_offers",
                           return_value=[_unverified_offer()]):
        dc._augment_gap_devices_with_verified_catalog(results, contexts, None)

    assert results[0]["offers"] == [], "unverified catalog match must NOT be surfaced"
    assert results[0]["status"] == "none"


def test_augment_skips_device_without_hwid() -> None:
    # No VEN_ in instance id → cannot HWID-verify → must not even call the catalog.
    ctx = dict(PCI_CTX)
    ctx["instance_id"] = "ROOT\\SYSTEM\\0001"
    results = [{"device_name": "Pseudo", "installed_version": "1.0",
                "offers": [], "status": "none"}]
    contexts = {"Pseudo": ctx}
    fetch = mock.MagicMock(return_value=[_verified_offer()])

    with mock.patch.object(dc, "_v6_catalog_enabled", return_value=True), \
         mock.patch.object(dc, "is_quick_check_mode", return_value=False), \
         mock.patch.object(dc, "_gui_gap_catalog_fallback_enabled", return_value=True), \
         mock.patch.object(dc, "fetch_microsoft_catalog_search_offers", fetch):
        dc._augment_gap_devices_with_verified_catalog(results, contexts, None)

    assert results[0]["offers"] == []
    fetch.assert_not_called()


def test_augment_leaves_covered_device_untouched() -> None:
    existing = [{"source": "oem", "title": "Dell driver", "version": "9.9"}]
    results = [{"device_name": "Covered", "installed_version": "1.0",
                "offers": list(existing), "status": "newer"}]
    contexts = {"Covered": dict(PCI_CTX)}
    fetch = mock.MagicMock(return_value=[_verified_offer()])

    with mock.patch.object(dc, "_v6_catalog_enabled", return_value=True), \
         mock.patch.object(dc, "is_quick_check_mode", return_value=False), \
         mock.patch.object(dc, "_gui_gap_catalog_fallback_enabled", return_value=True), \
         mock.patch.object(dc, "fetch_microsoft_catalog_search_offers", fetch):
        dc._augment_gap_devices_with_verified_catalog(results, contexts, None)

    assert results[0]["offers"] == existing, "covered device must be untouched"
    fetch.assert_not_called()


def test_augment_noop_when_disabled() -> None:
    results = [{"device_name": "Intel I225-V", "installed_version": "1.0",
                "offers": [], "status": "none"}]
    contexts = {"Intel I225-V": dict(PCI_CTX)}
    fetch = mock.MagicMock(return_value=[_verified_offer()])

    with mock.patch.object(dc, "_v6_catalog_enabled", return_value=True), \
         mock.patch.object(dc, "is_quick_check_mode", return_value=False), \
         mock.patch.object(dc, "_gui_gap_catalog_fallback_enabled", return_value=False), \
         mock.patch.object(dc, "fetch_microsoft_catalog_search_offers", fetch):
        dc._augment_gap_devices_with_verified_catalog(results, contexts, None)

    assert results[0]["offers"] == []
    fetch.assert_not_called()


if __name__ == "__main__":
    test_gap_name_queries_drop_hwid_and_generic()
    test_gap_name_queries_empty_for_generic_label()
    test_augment_attaches_verified_offer()
    test_augment_rejects_unverified_offer()
    test_augment_skips_device_without_hwid()
    test_augment_leaves_covered_device_untouched()
    test_augment_noop_when_disabled()
    print("gap catalog fallback tests OK")
