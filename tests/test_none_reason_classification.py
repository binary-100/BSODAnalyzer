"""None-status classification and Intel MSCatalog query helpers."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import driver_catalog as dc


def test_classify_standard_inbox_device() -> None:
    ctx = {
        "device_label": "Standard PS/2 Keyboard",
        "pnp_class": "keyboard",
        "manufacturer": "(Standard keyboards)",
        "primary_version": "10.0.26100.1",
    }
    reason = dc.classify_none_reason(ctx, [], status="none")
    assert reason == "standard_device"
    assert not dc.possible_coverage_gap("10.0.26100.1", [], status="none", device_ctx=ctx)


def test_classify_chipset_component() -> None:
    ctx = {
        "device_label": "Intel(R) Serial IO I2C Host Controller",
        "vendor_key": "intel",
        "pnp_class": "system",
        "primary_version": "10.1.1.38",
    }
    reason = dc.classify_none_reason(ctx, [], status="none")
    assert reason == "chipset_component"
    assert not dc.possible_coverage_gap("10.1.1.38", [], status="none", device_ctx=ctx)


def test_intel_wifi_mscatalog_queries() -> None:
    ctx = {
        "vendor_key": "intel",
        "device_label": "Intel(R) Dual Band Wireless-AC 8265",
        "pnp_class": "net",
        "_batch_driver_check": True,
    }
    base = dc._catalog_search_queries_for_ctx({**ctx, "_batch_driver_check": False})
    batch = dc._batch_mscatalog_queries_for_ctx(ctx, base)
    assert any("Intel" in q for q in batch)
    assert any("8265" in q or "Wireless" in q for q in batch)


def test_none_reason_display_labels() -> None:
    assert dc.none_reason_display_label("standard_device") == "Standard / inbox"
    assert dc.none_reason_display_label("chipset_component") == "Chipset component"


if __name__ == "__main__":
    test_classify_standard_inbox_device()
    test_classify_chipset_component()
    test_intel_wifi_mscatalog_queries()
    test_none_reason_display_labels()
    print("OK")
