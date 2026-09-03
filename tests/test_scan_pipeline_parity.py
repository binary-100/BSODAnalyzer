"""Scan pipeline parity — vendor warm, chipset plumbing, install-probe cache."""
from __future__ import annotations

from unittest import mock

import driver_catalog as dc


def test_intel_chipset_plumbing_uses_chipset_catalog_tier() -> None:
    ctx = {
        "device_label": "Intel(R) 100 Series/C230 Series Chipset Family LPC Controller (HM170) - A14E",
        "vendor_key": "intel",
        "pnp_class": "system",
    }
    assert dc._device_is_intel_chipset_plumbing(ctx)
    assert dc._ctx_is_chipset_catalog(ctx)
    assert dc._ctx_is_chipset_component_plumbing(ctx)


def test_chipset_platform_row_not_component_plumbing() -> None:
    ctx = {
        "device_name": "__chipset_intel_platform__",
        "hw_category": "chipset",
        "vendor_key": "intel",
    }
    assert dc._ctx_is_chipset_catalog(ctx)
    assert not dc._ctx_is_chipset_component_plumbing(ctx)


def test_chipset_component_plumbing_skips_manufacturer_tasks() -> None:
    ctx = {
        "device_label": "Intel(R) PCI Express Root Port #3 - A112",
        "vendor_key": "intel",
        "pnp_class": "system",
    }
    with mock.patch.object(dc, "_manufacturer_vendor_lookup_applicable", return_value=True):
        tasks = dc._manufacturer_catalog_tasks_for_ctx(ctx, {"cpu_vendor": "intel"})
    assert "intel" not in tasks


def test_install_probe_cache_dedupes_same_url() -> None:
    dc.clear_install_probe_cache()
    offer = {
        "source": "vendor",
        "source_label": "Manufacturer (Intel)",
        "url": "https://www.intel.com/content/www/us/en/download/19347/chipset.html",
        "version": "10.1.20398",
    }
    calls = {"n": 0}

    def fake_resolve(url: str, row: dict | None) -> tuple[bool, str, str]:
        del url, row
        calls["n"] += 1
        return True, "", "https://downloadmirror.intel.com/example/SetupChipset.exe"

    with mock.patch.object(dc, "resolve_vendor_package_download_url", side_effect=fake_resolve):
        first = dc._probe_offer_install_path(dict(offer))
        second = dc._probe_offer_install_path(dict(offer))
    assert calls["n"] == 1
    assert first.get("install_verified") is True
    assert second.get("install_verified") is True


if __name__ == "__main__":
    test_intel_chipset_plumbing_uses_chipset_catalog_tier()
    test_chipset_platform_row_not_component_plumbing()
    test_chipset_component_plumbing_skips_manufacturer_tasks()
    test_install_probe_cache_dedupes_same_url()
    print("scan pipeline parity tests OK")
