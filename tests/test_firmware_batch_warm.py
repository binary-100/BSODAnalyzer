"""Tests for firmware batch warm + peripheral search dedupe."""

from __future__ import annotations

import json
import os
import sys
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import firmware_peripheral_vendors as fpv
import vendor_firmware_fetch as vff


def test_zendesk_search_dedupes_via_cache() -> None:
    cache: dict[str, str] = {}
    payload = {"results": [{"id": 1, "title": "MX Keys firmware", "snippet": "firmware 1.2"}]}

    with mock.patch.object(
        fpv, "_robust_get_json", return_value=(True, json.dumps(payload))
    ) as fetch:
        first = fpv.search_zendesk_articles(
            "https://support.logi.com", "MX Keys firmware", cache=cache
        )
        second = fpv.search_zendesk_articles(
            "https://support.logi.com", "MX Keys firmware", cache=cache
        )
    assert len(first) == 1
    assert second == first
    assert fetch.call_count == 1


def test_warm_peripheral_search_cache_dedupes_queries() -> None:
    cache: dict[str, str] = {}
    devices = [
        {
            "category": "usb_peripheral",
            "vendor_key": "logitech",
            "device_id": "USB\\VID_046D&PID_C52B",
            "resolved_name": "Logitech MX Keys",
            "subcategory": "keyboard",
        },
        {
            "category": "usb_peripheral",
            "vendor_key": "logitech",
            "device_id": "USB\\VID_046D&PID_C52F",
            "resolved_name": "Logitech MX Keys Mini",
            "subcategory": "keyboard",
        },
    ]
    with mock.patch.object(
        fpv, "search_zendesk_articles", return_value=[]
    ) as search:
        fpv.warm_peripheral_search_cache(devices, cache)
    # Same vendor + overlapping queries should not explode call count.
    assert 0 < search.call_count <= 16


def test_warm_firmware_batch_orchestrates_layers() -> None:
    cache: dict[str, str] = {}
    with mock.patch.object(vff, "warm_oem_catalogs_parallel") as oem, mock.patch.object(
        vff, "warm_ssd_vendor_pages"
    ) as ssd, mock.patch(
        "firmware_peripheral_vendors.warm_peripheral_search_cache"
    ) as periph:
        vff.warm_firmware_batch(
            {"system_manufacturer": "ASUSTeK"},
            ssd_drives=[{"vendor_key": "samsung", "model": "990 PRO"}],
            secondary_devices=[{"category": "usb_peripheral", "vendor_key": "razer"}],
            scan_cache=cache,
        )
    oem.assert_called_once()
    ssd.assert_called_once()
    periph.assert_called_once()


if __name__ == "__main__":
    test_zendesk_search_dedupes_via_cache()
    test_warm_peripheral_search_cache_dedupes_queries()
    test_warm_firmware_batch_orchestrates_layers()
    print("OK")
