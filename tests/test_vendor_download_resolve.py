"""Direct vendor download URL resolver (Realtek ToDownload, Intel mirror pages)."""

from __future__ import annotations

from unittest import mock

import vendor_download_resolve as vdr


def test_path_is_package_detects_exe_and_zip() -> None:
    assert vdr._path_is_package("https://x.example/foo.exe")
    assert vdr._path_is_package("https://x.example/pkg.zip?token=1")
    assert not vdr._path_is_package("https://realtek.com/Download/List")


def test_resolve_realtek_already_direct() -> None:
    ok, err, url = vdr.resolve_realtek_download_url(
        "https://www.realtek.com/download/direct/Setup.exe"
    )
    assert ok
    assert not err
    assert url.endswith(".exe")


def test_resolve_realtek_todownload_follows_redirect() -> None:
    with mock.patch.object(
        vdr,
        "resolve_http_redirect_url",
        return_value=(True, "https://www.realtek.com/files/Setup.zip"),
    ):
        ok, err, url = vdr.resolve_realtek_download_url(
            "https://www.realtek.com/Download/ToDownload?type=direct&downloadid=1"
        )
    assert ok
    assert url.endswith(".zip")
    assert not err


def test_resolve_intel_extracts_mirror_from_html() -> None:
    html = (
        '<a href="https://downloadmirror.intel.com/12345/SetupChipset.exe">Download</a>'
    )
    with mock.patch.object(
        vdr,
        "resolve_http_redirect_url",
        return_value=(False, ""),
    ):
        pkg = vdr._extract_package_url_from_html(
            html,
            "https://www.intel.com/content/www/us/en/download/19347/chipset.html",
        )
    assert pkg.endswith("SetupChipset.exe")


def test_resolve_vendor_package_realtek_branch() -> None:
    with mock.patch.object(
        vdr,
        "resolve_realtek_download_url",
        return_value=(True, "", "https://www.realtek.com/files/nic.zip"),
    ):
        ok, err, url = vdr.resolve_vendor_package_download_url(
            "https://www.realtek.com/Download/ToDownload?type=direct&downloadid=9",
            {"source_label": "Manufacturer (Realtek)"},
        )
    assert ok and url.endswith(".zip")


def test_intel_chipset_suite_mismatch_compare() -> None:
    import driver_catalog as dc

    assert dc._intel_suite_vs_component_version_mismatch(
        "10.1.20398.8776", "10.1.1.45"
    )
    assert not dc._intel_suite_vs_component_version_mismatch(
        "10.1.20398.8776", "10.1.19900.8770"
    )
    vs, note = dc.compare_driver_to_installed("10.1.1.45", "10.1.20398.8776")
    assert vs == "uncertain"
    assert "Chipset INF suite" in note


def test_logitech_virtual_excluded_from_driver_scan() -> None:
    import driver_catalog as dc

    assert dc.is_driver_scan_excluded_device({
        "name": "Logitech G HUB Virtual Keyboard",
    })
    offers = dc.fetch_logitech_driver_offers({
        "vendor_key": "logitech",
        "device_label": "Logitech G HUB Virtual Keyboard",
    })
    assert offers == []


def test_intel_chipset_inf_does_not_drive_plumbing_status() -> None:
    import driver_catalog as dc

    ctx = {
        "device_label": "intel(r) pci express root port #1 - 1901",
        "vendor_key": "intel",
        "pnp_class": "system",
    }
    offers = dc.enrich_offers_with_comparison(
        [{
            "source": "vendor",
            "source_label": "Manufacturer (Intel)",
            "title": "Intel Chipset INF Software",
            "version": "10.1.20398.8776",
            "date": "2024-01-01",
            "url": "https://www.intel.com/download/19347",
        }],
        "10.1.1.45",
        device_ctx=ctx,
    )
    assert offers[0].get("informational_only")
    assert dc.summarize_offer_status(offers, device_ctx=ctx) == "none"


def test_sort_catalog_offers_prefers_installable() -> None:
    import driver_catalog as dc

    offers = dc.sort_catalog_offers([
        {
            "source": "vendor",
            "vs_installed": "newer",
            "url": "https://www.realtek.com/Download/List",
            "download_kind": "url",
            "title": "web",
        },
        {
            "source": "microsoft",
            "vs_installed": "newer",
            "url": "https://catalog/update.cab",
            "download_kind": "cab",
            "update_id": "abc",
            "title": "cab",
        },
    ])
    assert offers[0]["title"] == "cab"


def test_extract_intel_direct_from_mirror_link() -> None:
    html = (
        '<a href="https://downloadmirror.intel.com/12345/SetupChipset.exe">Download</a>'
    )
    url = vdr.extract_intel_direct_download_url(
        html,
        "https://www.intel.com/content/www/us/en/download/19347/chipset.html",
        "SetupChipset.exe",
    )
    assert url.endswith("SetupChipset.exe")


def test_extract_intel_direct_from_installer_filename() -> None:
    html = 'Download <a href="/content/dam/support/us/en/documents/inf/WiFi-23.50.0.exe">WiFi-23.50.0.exe</a>'
    url = vdr.extract_intel_direct_download_url(
        html,
        "https://www.intel.com/content/www/us/en/download/19351/wifi.html",
        "WiFi-23.50.0.exe",
    )
    assert url.endswith("WiFi-23.50.0.exe")


def test_intel_newer_without_installer_is_uncertain() -> None:
    import driver_catalog as dc

    offers = dc.enrich_offers_with_comparison(
        [{
            "source": "vendor",
            "source_label": "Manufacturer (Intel)",
            "title": "Intel Wi-Fi drivers",
            "version": "24.50.0.4",
            "date": "2024-01-01",
            "url": "https://www.intel.com/content/www/us/en/download/19351/wifi.html",
        }],
        "23.40.0.4",
        device_ctx={
            "vendor_key": "intel",
            "pnp_class": "net",
            "device_label": "Intel(R) Wi-Fi 6 AX201",
        },
    )
    assert offers[0]["vs_installed"] == "uncertain"
    assert "verified installer" in offers[0]["compare_note"]


def test_intel_newer_with_direct_installer_stays_newer() -> None:
    import driver_catalog as dc

    ctx = {
        "vendor_key": "intel",
        "hw_category": "chipset",
        "device_name": "__chipset_intel_platform__",
        "device_label": "Intel Chipset / Platform drivers",
    }
    offers = dc.enrich_offers_with_comparison(
        [{
            "source": "vendor",
            "source_label": "Manufacturer (Intel)",
            "title": "Intel Chipset INF utility",
            "version": "10.1.20398.8776",
            "date": "2024-01-01",
            "url": "https://downloadmirror.intel.com/999/SetupChipset.exe",
            "install_verified": True,
        }],
        "10.1.19900.8770",
        device_ctx=ctx,
    )
    assert offers[0]["vs_installed"] == "newer"
    assert dc.summarize_offer_status(offers, device_ctx=ctx) == "newer"


if __name__ == "__main__":
    test_path_is_package_detects_exe_and_zip()
    test_resolve_realtek_already_direct()
    test_resolve_realtek_todownload_follows_redirect()
    test_resolve_intel_extracts_mirror_from_html()
    test_resolve_vendor_package_realtek_branch()
    test_intel_chipset_suite_mismatch_compare()
    test_logitech_virtual_excluded_from_driver_scan()
    test_intel_chipset_inf_does_not_drive_plumbing_status()
    test_sort_catalog_offers_prefers_installable()
    test_extract_intel_direct_from_mirror_link()
    test_extract_intel_direct_from_installer_filename()
    test_intel_newer_without_installer_is_uncertain()
    test_intel_newer_with_direct_installer_stays_newer()
    print("vendor_download_resolve tests OK")
