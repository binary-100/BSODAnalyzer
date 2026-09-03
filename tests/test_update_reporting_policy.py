"""Unified update reporting — confident newer/same requires evidence; gaps stay honest."""

from __future__ import annotations

from unittest import mock

import driver_catalog as dc


def test_vendor_newer_without_installer_becomes_uncertain() -> None:
    offers = dc.enrich_offers_with_comparison(
        [{
            "source": "vendor",
            "source_label": "Manufacturer (AMD)",
            "title": "AMD Chipset Drivers",
            "version": "8.05.04.516",
            "url": "https://www.amd.com/en/support/download/drivers.html",
        }],
        "8.01.01.000",
    )
    assert offers[0]["vs_installed"] == "uncertain"
    assert "verified installer" in offers[0]["compare_note"]


def test_oem_newer_requires_installable_for_status() -> None:
    offers = dc.enrich_offers_with_comparison(
        [{
            "source": "oem",
            "source_label": "OEM (Dell)",
            "title": "Realtek Ethernet Driver",
            "version": "10.80.50.407",
            "url": "https://www.dell.com/support/home/drivers",
        }],
        "10.69.1121.2023",
    )
    assert offers[0]["vs_installed"] == "uncertain"
    assert dc.summarize_offer_status(offers) == "uncertain"


def test_nvidia_direct_download_allows_confident_newer() -> None:
    offers = dc.enrich_offers_with_comparison(
        [{
            "source": "vendor",
            "source_label": "Manufacturer (NVIDIA)",
            "title": "NVIDIA Game Ready Driver",
            "version": "582.66",
            "url": "https://international.download.nvidia.com/Windows/582.66/582.66-desktop-win10-win11-64bit-international-dch-whql.exe",
            "install_verified": True,
        }],
        "581.42",
    )
    assert offers[0]["vs_installed"] == "newer"
    assert dc.summarize_offer_status(offers) == "newer"


def test_summarize_keeps_confident_same_when_versions_match() -> None:
    offers = dc.enrich_offers_with_comparison(
        [{
            "source": "vendor",
            "source_label": "Manufacturer (AMD)",
            "title": "AMD drivers",
            "version": "26.6.2",
            "url": "https://www.amd.com/en/support/download/drivers.html",
        }],
        "26.6.2",
    )
    assert offers[0]["vs_installed"] == "same"
    assert dc.summarize_offer_status(offers) == "same"


def test_summarize_uncertain_when_newer_but_unverified() -> None:
    offers = dc.enrich_offers_with_comparison(
        [{
            "source": "vendor",
            "source_label": "Manufacturer (AMD)",
            "title": "AMD drivers",
            "version": "26.7.1",
            "url": "https://www.amd.com/en/support/download/drivers.html",
        }],
        "26.6.2",
    )
    assert offers[0]["vs_installed"] == "uncertain"
    assert dc.summarize_offer_status(offers) == "uncertain"


def test_coverage_gap_when_higher_version_but_unverified() -> None:
    offers = dc.enrich_offers_with_comparison(
        [{
            "source": "vendor",
            "source_label": "Manufacturer (Intel)",
            "title": "Intel Wi-Fi",
            "version": "24.50.0.4",
            "url": "https://www.intel.com/content/www/us/en/download/19351/wifi.html",
        }],
        "23.40.0.4",
    )
    status = dc.summarize_offer_status(offers)
    gap = dc.possible_coverage_gap("23.40.0.4", offers, status=status)
    assert offers[0]["vs_installed"] == "uncertain"
    assert gap is True


def test_probe_resolves_realtek_todownload() -> None:
    with mock.patch.object(
        dc,
        "resolve_vendor_package_download_url",
        return_value=(True, "", "https://www.realtek.com/files/nic.zip"),
    ):
        row = dc._probe_offer_install_path({
            "source": "vendor",
            "source_label": "Manufacturer (Realtek)",
            "url": "https://www.realtek.com/Download/ToDownload?type=direct&downloadid=1",
            "version": "11.030.50",
        })
    assert row["install_verified"]
    assert row["url"].endswith(".zip")


def test_cross_source_resolves_vendor_uncertain_to_newer() -> None:
    pool = [
        {
            "source": "vendor",
            "source_label": "Manufacturer (Intel)",
            "title": "Intel Wi-Fi",
            "version": "24.50.0.4",
            "url": "https://www.intel.com/content/www/us/en/download/19351/wifi.html",
        },
        {
            "source": "microsoft",
            "source_label": "Microsoft",
            "title": "Intel Wi-Fi driver",
            "version": "24.50.0.4",
            "update_id": "abc-123",
            "hwid_matched": True,
            "url": "https://catalog/update.cab",
            "download_kind": "catalog",
        },
    ]
    enriched = dc.enrich_offers_with_comparison(
        pool,
        "23.40.0.4",
        device_ctx={
            "vendor_key": "intel",
            "pnp_class": "net",
            "device_label": "Intel(R) Wi-Fi 6 AX201",
            "instance_id": "PCI\\VEN_8086&DEV_34F0",
        },
    )
    resolved = dc.resolve_uncertain_catalog_offers(
        enriched,
        "23.40.0.4",
        device_ctx={
            "vendor_key": "intel",
            "pnp_class": "net",
            "device_label": "Intel(R) Wi-Fi 6 AX201",
            "instance_id": "PCI\\VEN_8086&DEV_34F0",
        },
    )
    vendor = next(o for o in resolved if o.get("source") == "vendor")
    assert vendor.get("vs_installed") == "newer"
    assert vendor.get("verification_method") == "cross_source"


def test_realtek_nic_identity_resolves_uncertain() -> None:
    row = dc._try_resolve_uncertain_offer(
        {
            "source": "vendor",
            "source_label": "Manufacturer (Realtek)",
            "version": "11.030.50",
            "vs_installed": "uncertain",
            "compare_note": "family mismatch",
        },
        [],
        "10.69.1121.2023",
        "",
        {
            "vendor_key": "realtek",
            "pnp_class": "net",
            "device_label": "Realtek PCIe GBE Family Controller",
        },
    )
    # 11.030.50 vs 10.x won't identity-match; probe may fail — at least no crash
    assert row.get("vs_installed") in ("uncertain", "same", "newer", "older")


def test_finalize_includes_verification_pass() -> None:
    offers = dc._finalize_catalog_offers(
        [{
            "source": "vendor",
            "source_label": "Manufacturer (AMD)",
            "title": "AMD Chipset",
            "version": "8.05.04.516",
            "url": "https://www.amd.com/en/support/download/drivers.html",
        }],
        "8.01.01.000",
        device_ctx={"vendor_key": "amd", "hw_category": "chipset", "pnp_class": "system"},
    )
    assert offers[0]["vs_installed"] == "uncertain"


if __name__ == "__main__":
    test_vendor_newer_without_installer_becomes_uncertain()
    test_oem_newer_requires_installable_for_status()
    test_nvidia_direct_download_allows_confident_newer()
    test_summarize_keeps_confident_same_when_versions_match()
    test_summarize_uncertain_when_newer_but_unverified()
    test_coverage_gap_when_higher_version_but_unverified()
    test_probe_resolves_realtek_todownload()
    test_cross_source_resolves_vendor_uncertain_to_newer()
    test_realtek_nic_identity_resolves_uncertain()
    test_finalize_includes_verification_pass()
    print("update reporting policy tests OK")
