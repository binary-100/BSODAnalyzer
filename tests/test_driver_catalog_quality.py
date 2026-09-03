"""Catalog quality: firmware exclusion, MSCatalog filtering, Microsoft deferral, inbox versions."""

from __future__ import annotations

import os
import urllib.parse
from unittest import mock

# The manufacturer-tier tests patch _manufacturer_catalog_tasks_for_ctx on cdc, not on the
# driver_catalog re-export: _build_device_comparison_from_ctx calls it as a module-level
# name, so patching the facade leaves the test making real vendor network calls.
import catalog_amd_fetch as caf
import catalog_device_comparison as cdc
import catalog_download as cdl
import catalog_scoring as cs
import driver_catalog as dc
import bsod_analyzer as core


def test_firmware_class_excluded_from_driver_scan() -> None:
    ctx = {
        "pnp_class": "FIRMWARE",
        "device_label": "Device Firmware",
        "installed_rows": [{"device_class": "FIRMWARE", "version": "10.0.26100.4768"}],
    }
    assert dc.is_driver_scan_excluded_ctx(ctx)
    assert dc.is_driver_scan_excluded_device({"name": "Device Firmware", "device_class": "FIRMWARE"})


def test_reject_hp_firmware_on_dell_system() -> None:
    row = {"title": "HP Inc. Firmware Driver Update (10.0.26100.4768)"}
    ctx = {
        "system_manufacturer": "Dell Inc.",
        "pnp_class": "USB",
        "device_label": "USB Root Hub",
        "instance_id": "PCI\\VEN_1022&DEV_15B8",
    }
    assert dc._reject_mscatalog_row_for_ctx(row, ctx, "USB Root Hub") == "cross_oem"


def test_reject_kaspersky_on_audio_endpoint() -> None:
    row = {"title": "Kaspersky ActivityMonitor Driver Update (30.1945.0.12857)"}
    ctx = {
        "pnp_class": "AUDIOENDPOINT",
        "device_label": "Audio Endpoint",
        "vendor_key": "",
        "instance_id": "",
    }
    assert dc._reject_mscatalog_row_for_ctx(row, ctx, "Audio Endpoint") == "security_software"


def test_reject_firmware_package_on_normal_driver_device() -> None:
    row = {"title": "Intel System Firmware Update Package"}
    ctx = {"pnp_class": "net", "device_label": "Intel Wi-Fi 6", "system_manufacturer": "Dell Inc."}
    assert dc._reject_mscatalog_row_for_ctx(row, ctx, "Intel Wi-Fi") == "firmware_package"


def test_filter_hides_informational_microsoft_rows() -> None:
    offers = dc.enrich_offers_with_comparison(
        [
            {
                "source": "microsoft",
                "title": "No optional driver updates pending",
                "version": "",
                "download_kind": "uri",
                "informational": True,
            },
            {
                "source": "oem",
                "title": "Realtek Audio Driver",
                "version": "6.0.9200.0",
            },
        ],
        "6.0.9126.1",
    )
    shown = dc.filter_offers_for_display(offers)
    assert len(shown) == 1
    assert shown[0]["source"] == "oem"


def test_inbox_vs_vendor_version_is_uncertain_without_hwid() -> None:
    vs, note = dc.compare_driver_to_installed(
        "10.0.26100.1150",
        "32.0.15.9579",
        hwid_verified=False,
    )
    assert vs == "uncertain"
    assert "inbox" in note.lower()


def test_inbox_vs_vendor_allowed_when_hwid_verified() -> None:
    vs, _note = dc.compare_driver_to_installed(
        "10.0.26100.1150",
        "32.0.15.9579",
        hwid_verified=True,
    )
    assert vs == "newer"


def test_has_actionable_versioned_offer_skips_support_link() -> None:
    offers = [
        {"source": "oem", "title": "Dell support", "version": "", "confidence": "low"},
        {"source": "microsoft", "title": "Catalog hit", "version": "99.0.0.0"},
    ]
    assert not dc.has_actionable_versioned_offer(offers)
    offers.append({"source": "vendor", "title": "AMD Driver", "version": "24.10.1"})
    assert dc.has_actionable_versioned_offer(offers)


def test_microsoft_deferred_when_vendor_has_version() -> None:
    from unittest import mock

    calls: list[bool] = []

    def fake_fetch(ctx, **kwargs):
        calls.append(kwargs.get("allow_catalog_search", True))
        return []

    ctx = {
        "primary_version": "24.9.0",
        "device_label": "AMD Radeon Graphics",
        "pnp_class": "display",
        "installed_rows": [],
    }
    with mock.patch.object(dc, "fetch_microsoft_driver_offers", side_effect=fake_fetch), mock.patch.object(
        cdc,
        "_manufacturer_catalog_tasks_for_ctx",
        return_value={
            "vendor": lambda: [{"source": "vendor", "title": "AMD", "version": "24.10.1"}],
        },
    ), mock.patch.object(dc, "_should_skip_oem_after_manufacturer_tier", return_value=True):
        dc._build_device_comparison_from_ctx(ctx, {"system_manufacturer": "Dell Inc."})
    assert calls == [False]


def test_tiered_search_skips_oem_when_gpu_manufacturer_newer() -> None:
    ctx = {
        "primary_version": "580.0",
        "device_label": "NVIDIA GeForce RTX 4080",
        "pnp_class": "display",
        "vendor_key": "nvidia",
        "installed_rows": [],
    }
    mfr = [{
        "source": "vendor",
        "title": "NVIDIA Game Ready",
        "version": "581.42",
        "confidence": "high",
    }]
    with mock.patch.object(
        cdc,
        "_manufacturer_catalog_tasks_for_ctx",
        return_value={"nvidia": lambda: list(mfr)},
    ), mock.patch.object(dc, "fetch_oem_driver_offers") as oem, mock.patch.object(
        dc, "fetch_microsoft_driver_offers", return_value=[]
    ):
        dc._build_device_comparison_from_ctx(ctx, {"system_manufacturer": "Dell Inc."})
    oem.assert_not_called()


def test_gpu_mscatalog_fallback_when_manufacturer_uncertain() -> None:
    ctx = {
        "primary_version": "32.0.101.6127",
        "device_label": "Intel(R) UHD Graphics 630",
        "pnp_class": "display",
        "vendor_key": "intel",
        "instance_id": "PCI\\VEN_8086&DEV_3E92",
        "installed_rows": [],
    }
    mfr_uncertain = [{
        "source": "vendor",
        "source_label": "Manufacturer (Intel)",
        "title": "Intel Graphics",
        "version": "",
        "coverage_check_failed": True,
        "confidence": "low",
    }]
    ms_called: list[int] = []

    def fake_ms(*_a, **_k):
        ms_called.append(1)
        return []

    with mock.patch.object(
        cdc,
        "_manufacturer_catalog_tasks_for_ctx",
        return_value={"intel": lambda: list(mfr_uncertain)},
    ), mock.patch.object(dc, "fetch_oem_driver_offers") as oem, mock.patch.object(
        dc, "fetch_microsoft_driver_offers", side_effect=fake_ms
    ), mock.patch.object(
        dc, "fetch_microsoft_catalog_search_offers", return_value=[]
    ):
        dc._build_device_comparison_from_ctx(ctx, {"system_manufacturer": "ASUSTeK"})
    assert ms_called
    oem.assert_not_called()


def test_gpu_skips_mscatalog_when_manufacturer_has_version() -> None:
    ctx = {
        "primary_version": "32.0.101.6127",
        "device_label": "Intel(R) UHD Graphics 630",
        "pnp_class": "display",
        "vendor_key": "intel",
        "instance_id": "PCI\\VEN_8086&DEV_3E92",
        "installed_rows": [],
    }
    mfr_ok = [{
        "source": "vendor",
        "source_label": "Manufacturer (Intel)",
        "title": "Intel Graphics",
        "version": "32.0.101.7000",
        "confidence": "medium",
        # A versioned offer with no fetchable package re-enriches to "uncertain", which
        # would keep the Microsoft tier running and defeat the point of this test.
        "url": "https://downloadmirror.intel.com/1234/gfx_win_101.7000.exe",
    }]
    ms_called: list[int] = []

    def fake_ms(*_a, **_k):
        ms_called.append(1)
        return []

    with mock.patch.object(
        cdc,
        "_manufacturer_catalog_tasks_for_ctx",
        return_value={"intel": lambda: list(mfr_ok)},
    ), mock.patch.object(dc, "fetch_oem_driver_offers") as oem, mock.patch.object(
        dc, "fetch_microsoft_driver_offers", side_effect=fake_ms
    ), mock.patch.object(
        dc, "fetch_microsoft_catalog_search_offers", return_value=[]
    ):
        dc._build_device_comparison_from_ctx(ctx, {"system_manufacturer": "ASUSTeK"})
    assert not ms_called
    oem.assert_not_called()


def test_tiered_search_runs_oem_for_chipset_after_manufacturer() -> None:
    ctx = {
        "primary_version": "8.0",
        "device_label": "AMD Chipset",
        "hw_category": "chipset",
        "vendor_key": "amd",
        "installed_rows": [],
    }
    with mock.patch.object(
        cdc,
        "_manufacturer_catalog_tasks_for_ctx",
        return_value={
            "amd": lambda: [{
                "source": "vendor",
                "title": "AMD Chipset",
                "version": "8.05.04.600",
                "confidence": "medium",
            }],
        },
    ), mock.patch.object(
        dc, "fetch_oem_driver_offers", return_value=[{"source": "oem", "title": "Dell Chipset", "version": "8.05.04.600"}]
    ) as oem, mock.patch.object(dc, "fetch_microsoft_driver_offers", return_value=[]):
        dc._build_device_comparison_from_ctx(ctx, {"system_manufacturer": "Dell Inc."})
    oem.assert_called_once()


def test_should_skip_oem_primary_gpu_always() -> None:
    ctx = {"pnp_class": "display", "vendor_key": "nvidia", "device_label": "NVIDIA GPU", "installed_rows": []}
    same = [{"source": "vendor", "title": "NVIDIA", "version": "580.0", "confidence": "high"}]
    assert dc._should_skip_oem_after_manufacturer_tier(ctx, same, "580.0")
    newer = [{"source": "vendor", "title": "NVIDIA", "version": "581.0", "confidence": "high"}]
    assert dc._should_skip_oem_after_manufacturer_tier(ctx, newer, "580.0")
    empty: list[dict] = []
    assert dc._should_skip_oem_after_manufacturer_tier(ctx, empty, "580.0")


def test_tiered_search_skips_microsoft_for_primary_gpu() -> None:
    ctx = {
        "primary_version": "580.0",
        "device_label": "NVIDIA GeForce RTX 4080",
        "pnp_class": "display",
        "vendor_key": "nvidia",
        "installed_rows": [],
    }
    mfr = [{
        "source": "vendor",
        "title": "NVIDIA Game Ready",
        "version": "580.0",
        "confidence": "high",
    }]
    with mock.patch.object(
        cdc,
        "_manufacturer_catalog_tasks_for_ctx",
        return_value={"nvidia": lambda: list(mfr)},
    ), mock.patch.object(dc, "fetch_oem_driver_offers") as oem, mock.patch.object(
        dc, "fetch_microsoft_driver_offers", return_value=[]
    ) as ms, mock.patch.object(
        dc, "fetch_microsoft_catalog_search_offers", return_value=[]
    ) as mscat:
        dc._build_device_comparison_from_ctx(ctx, {"system_manufacturer": "Dell Inc."})
    oem.assert_not_called()
    ms.assert_not_called()
    # A cache_only probe is permitted — it reads the batch-warmed cache and issues no
    # query. What must not happen is a live MSCatalog search for a primary GPU.
    for call in mscat.call_args_list:
        assert call.kwargs.get("cache_only") is True, call


def test_mscatalog_batch_excludes_primary_gpu_display() -> None:
    contexts = {
        "gpu": {
            "instance_id": "PCI\\VEN_10DE&DEV_2484&SUBSYS_11111111&REV_A1",
            "device_label": "NVIDIA GeForce RTX",
            "vendor_key": "nvidia",
            "pnp_class": "display",
            "pci_tokens": ["VEN_10DE", "DEV_2484"],
        },
        "nic": {
            "instance_id": "PCI\\VEN_10EC&DEV_8125",
            "device_label": "Realtek PCIe 2.5GbE",
            "vendor_key": "realtek",
            "pnp_class": "net",
            "pci_tokens": ["VEN_10EC", "DEV_8125"],
        },
    }
    queries = dc._unique_mscatalog_queries_from_device_contexts(contexts)
    assert queries
    assert not any("VEN_10DE" in q for q in queries)
    assert any("10EC" in q or "Realtek" in q for q in queries)


def test_should_skip_oem_gpu_requires_confident_newer() -> None:
    """Non-primary-GPU network rows still require confident newer to skip OEM."""
    ctx = {"pnp_class": "net", "vendor_key": "qualcomm", "device_label": "Qualcomm Wi-Fi", "installed_rows": []}
    # Both rows carry a fetchable package so the only variable is the version:
    # _should_skip_oem_after_manufacturer_tier re-enriches the offers, and a versioned
    # row without an installer is downgraded to uncertain regardless of version.
    pkg = "https://www.qualcomm.com/downloads/wifi-driver.exe"
    same = [{"source": "vendor", "title": "Qualcomm", "version": "580.0", "confidence": "high", "url": pkg}]
    assert not dc._should_skip_oem_after_manufacturer_tier(ctx, same, "580.0")
    newer = [{"source": "vendor", "title": "Qualcomm", "version": "581.0", "confidence": "high", "url": pkg}]
    assert dc._should_skip_oem_after_manufacturer_tier(ctx, newer, "580.0")


def test_reject_amd_system_driver_on_monitor() -> None:
    row = {"title": "AMD System Driver Update (23.19.0.5)"}
    ctx = {
        "vendor_key": "amd",
        "pnp_class": "monitor",
        "device_label": "Dell Alienware 17 R5 AMD LGD06E3 Display",
        "instance_id": "MONITOR\\DELD0E3\\...",
    }
    assert dc._reject_mscatalog_row_for_ctx(row, ctx, "Dell Alienware") == "amd_system_driver_wrong_class"


def test_reject_amd_system_driver_on_streaming_audio() -> None:
    row = {"title": "AMD System Driver Update (23.19.0.5)"}
    ctx = {
        "vendor_key": "amd",
        "pnp_class": "media",
        "device_label": "AMD Streaming Audio Device",
        "instance_id": "",
    }
    assert dc._reject_mscatalog_row_for_ctx(row, ctx, "AMD Streaming Audio Device") == "amd_system_driver_wrong_class"


def test_allow_amd_system_driver_on_gpio_without_hwid() -> None:
    row = {"title": "AMD System Driver Update (23.19.0.5)"}
    ctx = {
        "vendor_key": "amd",
        "pnp_class": "system",
        "device_label": "AMD GPIO Controller",
        "instance_id": "ACPI\\AMDIF030\\0",
    }
    assert dc._reject_mscatalog_row_for_ctx(row, ctx, "AMD GPIO Controller") is None


def test_reject_amd_system_driver_on_audio_coprocessor() -> None:
    row = {"title": "AMD System Driver Update (7.0.3.60)"}
    ctx = {
        "vendor_key": "amd",
        "pnp_class": "system",
        "device_label": "AMD Audio CoProcessor",
        "instance_id": "",
    }
    assert dc._reject_mscatalog_row_for_ctx(row, ctx, "AMD Audio CoProcessor") == "amd_system_driver_wrong_class"


def test_reject_nvidia_display_on_virtual_audio() -> None:
    row = {"title": "NVIDIA Display Driver Update (32.0.15.8216)"}
    ctx = {
        "vendor_key": "nvidia",
        "pnp_class": "media",
        "device_label": "NVIDIA Virtual Audio Device (Wave Extensible) (WDM)",
        "instance_id": "",
    }
    assert dc._reject_mscatalog_row_for_ctx(row, ctx, "NVIDIA Virtual Audio") == "display_driver_on_audio_device"


def test_reject_apo_on_battery() -> None:
    row = {"title": "Microsoft Corporation AudioProcessingObject Driver Update (2.0.30.0)"}
    ctx = {
        "pnp_class": "",
        "device_label": "Microsoft Surface ACPI-Compliant Control Method Battery",
        "instance_id": "",
    }
    assert dc._reject_mscatalog_row_for_ctx(row, ctx, "Battery") == "component_driver_on_battery"


def test_realtek_wdm_vs_apo_version_uncertain() -> None:
    vs, note = dc.compare_driver_to_installed("6.0.9929.1", "13.0.6000.1905")
    assert vs == "uncertain"
    assert "numbering scheme" in note.lower()


def test_build_device_driver_comparison_skips_firmware() -> None:
    out = dc.build_device_driver_comparison(
        "Device Firmware",
        pnp_list=[{
            "Name": "Device Firmware",
            "DeviceID": "UEFI\\RES_{GUID}\\0",
            "PNPClass": "FIRMWARE",
        }],
        inventory=[{
            "name": "Device Firmware",
            "version": "10.0.26100.4768",
            "device_class": "FIRMWARE",
        }],
        system_ctx={"system_manufacturer": "Dell Inc."},
    )
    assert out.get("skipped_reason") == "firmware_class"
    assert out.get("offers") == []


def test_summarize_oem_authority_over_microsoft() -> None:
    offers = dc.enrich_offers_with_comparison(
        [
            {
                "source": "oem",
                "title": "Realtek Audio Driver",
                "version": "6.0.9126.1",
            },
            {
                "source": "microsoft",
                "title": "Realtek Audio",
                "version": "6.0.9200.0",
            },
        ],
        "6.0.9126.1",
    )
    assert dc.summarize_offer_status(offers) == "same"


def test_microsoft_newer_without_hwid_does_not_drive_status() -> None:
    offers = dc.enrich_offers_with_comparison(
        [
            {
                "source": "microsoft",
                "title": "Realtek Audio",
                "version": "6.0.9200.0",
            },
        ],
        "6.0.9126.1",
        device_ctx={"pnp_class": "media", "device_label": "Realtek Audio"},
    )
    assert offers[0]["vs_installed"] == "uncertain"
    assert dc.summarize_offer_status(offers) == "uncertain"


def test_microsoft_newer_with_hwid_drives_status() -> None:
    offers = dc.enrich_offers_with_comparison(
        [
            {
                "source": "microsoft",
                "title": "Realtek Audio",
                "version": "6.0.9200.0",
                "hwid_matched": True,
            },
        ],
        "6.0.9126.1",
    )
    assert offers[0]["vs_installed"] == "newer"
    assert dc.summarize_offer_status(offers) == "newer"


def test_oem_support_link_does_not_drive_newer_status() -> None:
    offers = dc.enrich_offers_with_comparison(
        [
            {
                "source": "oem",
                "title": "Dell Inc. support — Alienware m17 R5 AMD",
                "version": "",
                "url": "https://www.dell.com/support/",
            },
            {
                "source": "microsoft",
                "title": "Realtek Audio",
                "version": "6.0.9200.0",
                "hwid_matched": True,
            },
        ],
        "6.0.9126.1",
        device_ctx={"pnp_class": "media", "device_label": "Realtek Audio"},
    )
    assert dc.summarize_offer_status(offers) == "newer"
    assert dc.best_authoritative_offer(offers)["source"] == "microsoft"


def test_score_oem_row_prefers_versioned_device_match() -> None:
    ctx = {
        "pnp_class": "media",
        "device_label": "Realtek Audio",
        "vendor_key": "realtek",
    }
    good = {
        "title": "Realtek High Definition Audio Driver",
        "category": "Audio",
        "version": "6.0.9700.1",
    }
    generic = {
        "title": "Alienware support — Alienware m17 R5 AMD",
        "category": "",
        "version": "",
    }
    assert dc._score_oem_row_for_ctx(good, ctx) > dc._score_oem_row_for_ctx(generic, ctx)


def test_oem_gpu_not_offered_for_battery_or_keyboard() -> None:
    gpu_row = {
        "title": "AMD Radeon Graphics Driver",
        "category": "Video",
        "version": "32.0.11024.2",
    }
    battery_ctx = {
        "device_label": "Microsoft Surface ACPI-Compliant Control Method Battery",
        "pnp_class": "battery",
        "vendor_key": "surface",
    }
    keyboard_ctx = {
        "device_label": "Standard PS/2 Keyboard",
        "pnp_class": "keyboard",
        "vendor_key": "",
    }
    assert not dc._oem_row_eligible_for_ctx(gpu_row, battery_ctx)
    assert not dc._oem_row_eligible_for_ctx(gpu_row, keyboard_ctx)


def test_oem_gpu_not_offered_for_usb_hub_without_match() -> None:
    gpu_row = {
        "title": "AMD Radeon Graphics Driver",
        "version": "32.0.11024.2",
    }
    ctx = {
        "device_label": "USB Root Hub (USB 3.0)",
        "pnp_class": "usb",
        "vendor_key": "",
    }
    assert not dc._oem_row_eligible_for_ctx(gpu_row, ctx)


def test_oem_offers_from_rows_skips_unrelated_versioned_packages() -> None:
    rows = [
        {
            "title": "AMD Radeon Graphics Driver",
            "version": "32.0.11024.2",
            "url": "https://example.test/gpu",
            "category": "Video",
        },
        {
            "title": "Realtek High Definition Audio Driver",
            "version": "6.0.9738.1",
            "url": "https://example.test/audio",
            "category": "Audio",
        },
    ]
    ctx = {
        "device_label": "Realtek(R) Audio",
        "pnp_class": "media",
        "vendor_key": "realtek",
    }
    offers = dc._oem_offers_from_rows(
        rows,
        ctx,
        "OEM (Dell / Alienware)",
        "note",
        "https://dell.com/support",
    )
    assert len(offers) == 1
    assert "Realtek" in offers[0]["title"]


def test_filter_offers_drops_oem_gpu_on_peripheral() -> None:
    offers = [
        {
            "source": "oem",
            "title": "AMD Radeon Graphics Driver",
            "version": "32.0.11024.2",
        }
    ]
    ctx = {
        "device_label": "Microsoft Surface ACPI-Compliant Control Method Battery",
        "pnp_class": "battery",
        "vendor_key": "surface",
    }
    filtered = dc._filter_offers_for_device_ctx(offers, ctx)
    assert filtered == []


def test_oem_row_cache_is_per_system_not_per_device() -> None:
    dc.clear_oem_cache()
    dc.configure_catalog(oem_session_cache=True)
    nic_ctx = {
        "device_label": "Realtek Gaming 2.5GbE Family Controller",
        "pnp_class": "net",
        "vendor_key": "realtek",
        "primary_version": "1125.28.1224.2025",
    }
    chipset_ctx = {
        "device_label": "AMD Chipset / Platform drivers",
        "pnp_class": "system",
        "vendor_key": "amd",
        "hw_category": "chipset",
    }
    rows = [
        {
            "title": "Realtek Gaming 2.5GbE Family Controller Driver",
            "version": "1125.28.1224.2025",
            "category": "Network",
            "url": "https://example.test/nic-gaming",
        },
        {
            "title": "Realtek PCIe Ethernet Controller Driver",
            "version": "1168.28.1224.2025",
            "category": "Network",
            "url": "https://example.test/nic",
        },
        {
            "title": "AMD Chipset Driver",
            "version": "8.05.04.516",
            "category": "Chipset",
            "url": "https://example.test/chipset",
        },
    ]
    system_ctx = {"system_manufacturer": "Alienware", "system_model": "m17 R5 AMD"}
    with mock.patch.object(dc, "_fetch_dell_oem_rows_live", return_value=(rows, "https://dell.com/support")):
        gpu_first = dc.fetch_dell_oem_offers(chipset_ctx, system_ctx)
        nic_second = dc.fetch_dell_oem_offers(nic_ctx, system_ctx)
    assert any("1168.28" in (o.get("version") or "") for o in nic_second)
    assert not any("Radeon" in (o.get("title") or "") for o in gpu_first)


def test_batch_chipset_uses_registry_installed_version() -> None:
    try:
        from bsod_analyzer import CHIPSET_DEVICE_AMD
    except ImportError:
        CHIPSET_DEVICE_AMD = "__chipset_amd_platform__"
    dc.clear_installed_package_versions_cache()
    with mock.patch.object(dc, "_get_cached_wu_driver_rows", return_value=([], "")), mock.patch.object(
        dc, "ensure_mscatalog_module_ready", return_value=(True, "x")
    ), mock.patch.object(
        dc, "ensure_online_driver_store_loaded", return_value=None
    ), mock.patch.object(
        dc, "_load_installed_package_versions", return_value={"amd_chipset": "8.05.04.516"}
    ), mock.patch.object(
        dc, "fetch_amd_driver_offers", return_value=[]
    ), mock.patch.object(
        dc, "fetch_oem_driver_offers", return_value=[]
    ):
        batch = dc.build_multi_device_driver_comparison(
            [CHIPSET_DEVICE_AMD],
            [],
            [],
            {"system_manufacturer": "Alienware"},
        )
    assert batch["devices"][0]["installed_version"] == "8.05.04.516"


def test_needs_catalog_refresh_when_cache_missing() -> None:
    import catalog_cache as ccat

    with mock.patch.object(ccat, "_read_json", return_value=None):
        assert ccat.needs_catalog_refresh() is True


def test_normalize_oem_nested_dell_driverset() -> None:
    payload = {
        "DriverSet": [
            {
                "drivers": [
                    {
                        "title": "Realtek High Definition Audio Driver",
                        "version": "6.0.9700.1",
                        "downloadUrl": "https://example.test/audio.exe",
                    }
                ]
            }
        ]
    }
    rows = dc._normalize_oem_driver_rows(payload)
    assert len(rows) == 1
    assert rows[0]["version"] == "6.0.9700.1"


def test_normalize_oem_date_dell_release_string() -> None:
    row = dc._normalize_oem_driver_row_dict(
        {
            "title": "AMD Chipset Driver",
            "version": "7.12.30.210",
            "ReleaseDateString": "February 02, 2026",
            "downloadUrl": "https://www.dell.com/support/home/drivers",
        }
    )
    assert row is not None
    assert row["date"] == "2026-02-02"
    assert dc._normalize_oem_date("February 02, 2026") == "2026-02-02"
    assert dc._normalize_oem_date("February 0") == ""
    assert dc._normalize_oem_date("August 24, 2026") == "2026-08-24"
    assert dc._normalize_oem_date("2026-02-02") == "2026-02-02"
    assert dc._normalize_oem_date("June 30, 2") == ""


def test_fetch_oem_catalog_for_system_bulk_rows() -> None:
    rows = [
        {
            "title": "Realtek High Definition Audio Driver",
            "version": "6.0.9700.1",
            "date": "2024-01-01",
            "url": "https://example.test/audio.exe",
            "category": "Audio",
        }
    ]
    with mock.patch.object(dc, "get_dell_oem_rows", return_value=(rows, "https://dell.com/support")):
        offers = dc.fetch_oem_catalog_for_system({"system_manufacturer": "Alienware"})
    assert len(offers) == 1
    assert offers[0]["version"] == "6.0.9700.1"
    assert offers[0]["source_label"] == "OEM (Dell / Alienware)"


def test_fetch_oem_deep_uses_bulk_catalog() -> None:
    rows = [{"title": "AMD Chipset Driver", "version": "5.11.02.217", "url": "https://example.test/chipset.exe", "category": ""}]
    with mock.patch.object(dc, "get_dell_oem_rows", return_value=(rows, "https://dell.com")):
        offers = dc.fetch_oem_driver_offers_deep({"system_manufacturer": "Dell Inc.", "system_model": "XPS"})
    assert any(o.get("version") == "5.11.02.217" for o in offers)


def test_version_schemes_incompatible_audio_vs_gpu() -> None:
    assert dc._version_schemes_compatible("6.0.2.59", "32.0.11024.2") is False
    assert dc._version_schemes_compatible("10.0.1.42", "32.0.11024.2") is False
    assert dc._version_schemes_compatible("1.0.0.3", "26.6.1") is False
    assert dc._version_schemes_compatible("32.0.21043.19003", "26.6.4") is False


def test_register_amd_software_suite_without_chipset_in_name() -> None:
    out: dict[str, str] = {}
    dc._register_installed_package_from_name(out, "AMD Software", "8.07.16.1035")
    assert out.get("amd_chipset") == "8.07.16.1035"
    assert "amd_adrenalin" not in out


def test_amd_chipset_suite_version_heuristic() -> None:
    assert dc._looks_like_amd_chipset_package_version("8.05.04.516")
    assert dc._looks_like_amd_chipset_package_version("8.07.16.1035")
    assert dc._looks_like_amd_chipset_package_version("7.12.0.0")
    assert dc._looks_like_amd_chipset_package_version("5.11.02.217")
    assert not dc._looks_like_amd_chipset_package_version("5.44.0.0")
    assert not dc._looks_like_amd_chipset_package_version("5.12.0.44")
    assert not dc._looks_like_amd_chipset_package_version("8.0.0.62")
    assert not dc._looks_like_amd_chipset_package_version("2.2.0.137")


def test_chipset_version_profile_amd_plumbing() -> None:
    dev = {
        "device_class": "system",
        "vendor_key": "amd",
        "name": "AMD PSP 11.0 Device",
        "version": "5.44.0.0",
        "_installed_at_scan": "5.44.0.0",
        "_available_version": "8.05.04.516",
    }
    offers = [
        {
            "source_label": "AMD Chipset",
            "version": "8.05.04.516",
            "vs_installed": "newer",
        }
    ]
    with mock.patch.object(
        dc, "_load_amd_chipset_suite_installed_version", return_value="8.05.04.516"
    ):
        profile = dc.build_chipset_version_profile(dev, offers=offers)
    assert profile is not None
    assert profile["windows_installed"] == "5.44.0.0"
    assert profile["mfr_installed"] == "8.05.04.516"
    assert profile["mfr_available"] == "8.05.04.516"
    cell, tip = dc.format_chipset_installed_table_cell(profile)
    assert "5.44.0.0" in cell
    assert "Chipset 8.05.04.516" in cell
    assert "Device Manager" in tip
    sub = dc.format_chipset_version_subtitle(profile)
    assert "Windows (Device Manager): 5.44.0.0" in sub
    assert "AMD Chipset Software: 8.05.04.516" in sub


def test_chipset_platform_version_profile_amd() -> None:
    """Synthetic platform row lists suite + bundle component INFs (installer parity)."""
    try:
        from bsod_analyzer import CHIPSET_DEVICE_AMD
    except ImportError:
        CHIPSET_DEVICE_AMD = "__chipset_amd_platform__"
    inv = [
        {"display_name": "AMD PSP 11.0 Device", "version": "5.46.0.0"},
        {"display_name": "AMD SMBus Controller", "version": "5.12.0.44"},
        {"display_name": "AMD GPIO Controller", "version": "2.2.0.137"},
        {"display_name": "AMD I2C Controller", "version": "1.2.0.131"},
        {"display_name": "AMD MicroPEP Device", "version": "1.0.47.1"},
        {"display_name": "AMD Provisioning Packages", "version": "8.0.0.64"},
    ]
    dev = {
        "name": CHIPSET_DEVICE_AMD,
        "version": "8.07.16.1035",
        "_installed_at_scan": "8.07.16.1035",
    }
    offers = [{"source_label": "OEM (Dell / Alienware)", "version": "7.12.30.210"}]
    with mock.patch.object(
        dc, "_load_amd_chipset_suite_installed_version", return_value="8.07.16.1035"
    ):
        profile = dc.build_chipset_platform_version_profile(dev, offers=offers, inventory=inv)
    assert profile is not None
    assert profile["suite_installed"] == "8.07.16.1035"
    assert len(profile["components"]) == 6
    labels = {c["label"] for c in profile["components"]}
    assert labels == {"PSP", "SMBus", "GPIO", "I2C", "MicroPEP", "PPM"}
    cell, tip = dc.format_chipset_platform_installed_table_cell(profile)
    assert "8.07.16.1035" in cell
    assert "6 components" in cell
    assert "5.46.0.0" in tip
    sub = dc.format_chipset_platform_version_subtitle(profile)
    assert "8.07.16.1035" in sub
    assert "PSP" in sub or "5.46.0.0" in sub


def test_chipset_version_profile_not_on_synthetic_row() -> None:
    dev = {
        "name": "__chipset_amd_platform__",
        "version": "8.05.04.516",
        "_installed_at_scan": "8.05.04.516",
    }
    with mock.patch.object(
        dc, "_load_amd_chipset_suite_installed_version", return_value="8.05.04.516"
    ):
        assert dc.build_chipset_version_profile(dev) is None
        platform = dc.build_chipset_platform_version_profile(dev, inventory=[])
        assert platform is not None
        assert platform["suite_installed"] == "8.05.04.516"


def test_amd_psp_is_chipset_plumbing() -> None:
    assert dc._device_is_amd_chipset_plumbing({"device_label": "amd psp 11.0 device"})


def test_gpu_version_profile_amd() -> None:
    dev = {
        "device_class": "display",
        "vendor_key": "amd",
        "name": "AMD Radeon(TM) Graphics",
        "version": "32.0.21043.19003",
        "_installed_at_scan": "32.0.21043.19003",
        "_available_version": "26.6.4",
    }
    offers = [
        {
            "source_label": "Manufacturer (AMD)",
            "version": "26.6.4",
            "vs_installed": "newer",
        }
    ]
    with mock.patch.object(dc, "_load_amd_adrenalin_installed_version", return_value="26.6.2"):
        profile = dc.build_gpu_version_profile(dev, offers=offers)
    assert profile is not None
    assert profile["windows_installed"] == "32.0.21043.19003"
    assert profile["mfr_installed"] == "26.6.2"
    assert profile["mfr_available"] == "26.6.4"
    cell, tip = dc.format_gpu_installed_table_cell(profile)
    assert "32.0.21043.19003" in cell
    assert "Adrenalin 26.6.2" in cell
    assert "Device Manager" in tip
    sub = dc.format_gpu_version_subtitle(profile)
    assert "Windows (Device Manager): 32.0.21043.19003" in sub
    assert "26.6.2 → 26.6.4" in sub


def test_gpu_version_profile_nvidia() -> None:
    dev = {
        "device_class": "display",
        "vendor_key": "nvidia",
        "name": "NVIDIA GeForce RTX 3070 Ti Laptop GPU",
        "version": "32.0.16.1047",
        "_installed_at_scan": "32.0.16.1047",
        "_available_version": "610.74",
    }
    offers = [
        {
            "source_label": "Manufacturer (NVIDIA)",
            "version": "610.74",
            "windows_display_version": "32.0.17.1047",
            "vs_installed": "newer",
        }
    ]
    with mock.patch.object(dc, "_load_nvidia_branch_installed_version", return_value="581.42"):
        profile = dc.build_gpu_version_profile(dev, offers=offers)
    assert profile is not None
    assert profile["mfr_installed"] == "581.42"
    assert profile["mfr_available"] == "610.74"
    assert profile["windows_available"] == "32.0.17.1047"
    cell, _tip = dc.format_gpu_installed_table_cell(profile)
    assert "GRD branch 581.42" in cell


def test_amd_adrenalin_vs_display_driver_compare() -> None:
    with mock.patch.object(dc, "_load_amd_adrenalin_installed_version", return_value="26.6.2"):
        vs, note = dc.compare_driver_to_installed("32.0.21043.19003", "26.6.4")
    assert vs == "newer"
    assert "26.6.2" in note
    assert "26.6.4" in note


def test_amd_vendor_offer_not_dropped_when_display_version_newer() -> None:
    row = {
        "source": "vendor",
        "source_label": "Manufacturer (AMD)",
        "title": "AMD driver downloads",
        "version": "26.6.4",
        # Needed for "newer": a versioned offer with no fetchable installer is reported
        # as uncertain, and an uncertain vendor row is then dropped from display.
        "url": "https://drivers.amd.com/drivers/installer/adrenalin-26.6.4.exe",
    }
    ctx = {
        "pnp_class": "display",
        "device_label": "AMD Radeon(TM) Graphics",
        "vendor_key": "amd",
    }
    # Patch both the defining module and the facade: the compare path reads the module
    # global while the pipeline resolves the same helper lazily through driver_catalog.
    # With either one unpatched the test reads this host's real Adrenalin version and the
    # offer looks older, so the row is dropped and fin[0] raises IndexError.
    with mock.patch.object(cs, "_load_amd_adrenalin_installed_version", return_value="26.6.2"), \
         mock.patch.object(dc, "_load_amd_adrenalin_installed_version", return_value="26.6.2"):
        fin = dc._finalize_catalog_offers([row], "32.0.21043.19003", device_ctx=ctx)
    assert fin[0]["vs_installed"] == "newer"
    assert dc.summarize_offer_status(fin) == "newer"


def test_realtek_swc_rejected_on_wdm_even_with_hwid_match() -> None:
    ctx = {
        "pnp_class": "media",
        "device_label": "Realtek Audio",
        "vendor_key": "realtek",
        "instance_id": "HDAUDIO\\FUNC_01&VEN_10EC&DEV_0295&SUBSYS_10280B5B&REV_1000\\5&35e90671&0&0001",
        "pci_tokens": ["VEN_10EC", "DEV_0295", "SUBSYS_10280B5B"],
    }
    row = {
        "title": "Realtek Semiconductor Corp. SoftwareComponent Driver Update (10.0.0.12)",
        "version": "10.0.0.12",
        "products": "VEN_10EC&DEV_0295",
    }
    assert dc._reject_realtek_catalog_row(row, ctx) == "realtek_companion_on_wdm_device"


def test_realtek_stale_oem_does_not_block_microsoft_newer() -> None:
    oem = {
        "source": "oem",
        "source_label": "OEM (Dell / Alienware)",
        "title": "Realtek High Definition Audio Driver",
        "version": "6.0.9738.1",
    }
    ms = {
        "source": "microsoft",
        "title": "Realtek Semiconductor Corp. MEDIA Driver Update (6.0.9998.1)",
        "version": "6.0.9998.1",
        # Without HWID proof a Microsoft row cannot drive status at all (see
        # test_microsoft_newer_without_hwid_does_not_drive_status), which would make this
        # test pass for the wrong reason instead of proving the stale OEM row is ignored.
        "products": "VEN_10EC&DEV_0295&SUBSYS_10280B5B",
    }
    ctx = {
        "pnp_class": "media",
        "device_label": "Realtek Audio",
        "target_device_name": "Realtek Audio",
        "vendor_key": "realtek",
        "primary_version": "6.0.9929.1",
        "instance_id": "HDAUDIO\\FUNC_01&VEN_10EC&DEV_0295&SUBSYS_10280B5B&REV_1000\\5&35e90671&0&0001",
        "pci_tokens": ["VEN_10EC", "DEV_0295", "SUBSYS_10280B5B"],
    }
    fin = dc._finalize_catalog_offers([oem, ms], "6.0.9929.1", device_ctx=ctx)
    assert dc.summarize_offer_status(fin) == "newer"
    oem_row = next(o for o in fin if o.get("source") == "oem")
    assert oem_row.get("status_neutral") is True


def test_stale_realtek_oem_skips_source_conflict_flag() -> None:
    oem = {
        "source": "oem",
        "title": "Realtek High Definition Audio Driver",
        "version": "6.0.9738.1",
        "vs_installed": "same",
        "status_neutral": True,
    }
    ms = {
        "source": "microsoft",
        "title": "Realtek Semiconductor Corp. MEDIA Driver Update (6.0.10001.1)",
        "version": "6.0.10001.1",
        "vs_installed": "newer",
    }
    flagged = dc.annotate_offer_source_conflicts([oem, ms])
    assert not any(o.get("source_conflict") for o in flagged)


def test_amd_audio_coprocessor_rejects_realtek_hd_oem() -> None:
    row = {"title": "Realtek High Definition Audio Driver", "version": "6.0.9738.1"}
    ctx = {
        "vendor_key": "amd",
        "pnp_class": "system",
        "device_label": "AMD Audio CoProcessor",
    }
    assert dc._reject_oem_audio_vendor_mismatch(row, ctx) == "oem_audio_vendor_mismatch"


def test_find_pnp_entity_realtek_audio_prefers_codec_not_service() -> None:
    pnp = [
        {
            "Name": "Realtek Audio Universal Service",
            "DeviceID": r"SWD\X#SRV",
            "Parent": r"HDAUDIO\FUNC_01&VEN_10EC&DEV_0295\1",
        },
        {
            "Name": "Realtek(R) Audio",
            "DeviceID": r"HDAUDIO\FUNC_01&VEN_10EC&DEV_0295&SUBSYS_10280B5B&REV_1000\5&35e90671&0&0001",
            "Parent": "PCI\\ROOT",
        },
    ]
    hit = core._find_pnp_entity_by_device_name(pnp, "Realtek Audio")
    assert hit is not None
    assert hit.get("Name") == "Realtek(R) Audio"


def test_apply_realtek_parent_hwid_from_enrichment() -> None:
    ctx = {
        "vendor_key": "realtek",
        "device_label": "Realtek Audio",
        "target_device_name": "Realtek Audio",
        "pnp_class": "media",
        "instance_id": "",
        "pci_tokens": [],
    }
    parent = r"HDAUDIO\FUNC_01&VEN_10EC&DEV_0295&SUBSYS_10280B5B&REV_1000\5&35e90671&0&0001"
    system_ctx = {
        "pnp_enrichment": {
            "Realtek Audio": {"parent_device_id": parent},
        }
    }
    dc._apply_realtek_parent_hwid_ctx(ctx, [], system_ctx)
    assert "VEN_10EC" in ctx["instance_id"].upper()
    assert ctx["pci_tokens"]


def test_compare_audio_device_rejects_oem_graphics() -> None:
    ctx = {
        "device_label": "AMD Audio Device",
        "pnp_class": "media",
        "vendor_key": "amd",
    }
    row = {
        "title": "AMD Radeon Graphics Driver",
        "version": "32.0.11024.2",
        "source": "oem",
    }
    # A GPU-titled package is caught by the earlier "wrong device" rule, which covers every
    # non-GPU device class; only chipset-titled rows reach the audio-specific rule.
    assert dc._reject_vendor_driver_class_mismatch(row, ctx) == "gpu_driver_wrong_device"
    chipset = {"title": "AMD Chipset Driver", "version": "8.05.04.516", "source": "oem"}
    assert dc._reject_vendor_driver_class_mismatch(chipset, ctx) == "gpu_chipset_on_audio"


def test_amd_vendor_version_not_applicable_for_audio() -> None:
    ctx = {"vendor_key": "amd", "pnp_class": "media", "device_label": "AMD Audio Device"}
    assert dc._amd_vendor_version_lookup_applicable(ctx) is False
    offers = dc.fetch_amd_driver_offers(ctx)
    assert len(offers) == 1
    assert offers[0].get("version") == ""
    assert offers[0].get("informational_only") is True


def test_system_has_oem_driver_catalog() -> None:
    assert dc.system_has_oem_driver_catalog({"system_manufacturer": "Alienware"}) is True
    assert dc.system_has_oem_driver_catalog({"system_manufacturer": "ASRock"}) is False
    assert dc._oem_support_link_offers({"system_manufacturer": "ASRock"}, note="x") == []


def test_chipset_catalog_entry_resolves_registry_version() -> None:
    from bsod_hardware_wmi import CHIPSET_DEVICE_AMD, chipset_driver_catalog_entries

    ctx = {"has_amd_chipset": True, "cpu_vendor": "amd"}
    with mock.patch.object(
        dc, "_load_installed_package_versions", return_value={"amd_chipset": "8.05.04.516"}
    ):
        rows = chipset_driver_catalog_entries(ctx)
    assert len(rows) == 1
    assert rows[0]["name"] == CHIPSET_DEVICE_AMD
    assert rows[0]["version"] == "8.05.04.516"


def test_resolve_chipset_installed_version() -> None:
    with mock.patch.object(dc, "_load_installed_package_versions", return_value={}):
        inv = [{"display_name": "AMD Chipset Drivers", "version": "5.11.02.217"}]
        assert dc._resolve_chipset_installed_version("amd", inv) == "5.11.02.217"
        assert dc._resolve_chipset_installed_version("amd", []) == "?"

    with mock.patch.object(
        dc, "_load_installed_package_versions", return_value={"amd_chipset": "8.05.04.516"}
    ):
        assert dc._resolve_chipset_installed_version("amd", []) == "8.05.04.516"


def test_parse_dell_dup_manifest_sample() -> None:
    import tempfile
    sample = """<?xml version="1.0" encoding="utf-16"?>
<Manifest baseLocation="downloads.dell.com" xmlns="openmanage/cm/dm">
  <SoftwareComponent vendorVersion="1168.28.1224.2025" releaseID="GD26K" releaseDate="May 11, 2026"
    path="FOLDER14305413M/1/Realtek-PCIe-Ethernet-Controller-Driver_GD26K_WIN64_1168.28.1224.2025_A03.EXE">
    <Name><Display lang="en"><![CDATA[Realtek PCIe Ethernet Controller Driver]]></Display></Name>
    <Category value="NI"><Display lang="en"><![CDATA[Network]]></Display></Category>
    <SupportedDCHDevices>
      <Device componentID="103014" version="1125.028.1224.2025">
        <PCIInfo deviceID="8125" vendorID="10EC" subDeviceID="" subVendorID="" />
      </Device>
    </SupportedDCHDevices>
    <ImportantInfo URL="https://www.dell.com/support/home/us/en/19/Drivers/DriversDetails?driverId=GD26K"/>
  </SoftwareComponent>
  <SoftwareComponent vendorVersion="6.0.9738.1" releaseID="N3XT5" releaseDate="December 09, 2024">
    <Name><Display lang="en"><![CDATA[Realtek High Definition Audio Driver]]></Display></Name>
    <Category value="AU"><Display lang="en"><![CDATA[Audio]]></Display></Category>
  </SoftwareComponent>
</Manifest>"""
    with tempfile.NamedTemporaryFile("w", encoding="utf-16", suffix=".xml", delete=False) as fh:
        fh.write(sample)
        path = fh.name
    try:
        rows = dc._parse_dell_dup_manifest(path)
    finally:
        os.unlink(path)
    assert any(r["version"] == "1168.28.1224.2025" for r in rows)
    assert any("Realtek High Definition" in r["title"] for r in rows)
    eth = next(r for r in rows if r["version"] == "1168.28.1224.2025")
    assert eth["url"].startswith("https://downloads.dell.com/")
    assert eth["url"].lower().endswith(".exe")
    assert eth.get("inner_versions")
    assert eth["inner_versions"][0]["version"] == "1125.028.1224.2025"


def test_resolve_dell_driver_details_page() -> None:
    sample_html = """
    DellDndDrawer.FileDetails['2072383795']={FileId:'2072383795',
    FileLocation:'https://dl.dell.com/FOLDER14305413M/1/Realtek-PCIe-Ethernet-Controller-Driver_GD26K_WIN64_1168.28.1224.2025_A03.EXE'};
    """
    with mock.patch.object(dc, "_http_get", return_value=(True, sample_html)):
        ok, err, direct = dc._resolve_dell_driver_download_url(
            "https://www.dell.com/support/home/us/en/19/Drivers/DriversDetails?driverId=GD26K"
        )
    assert ok
    assert not err
    assert direct.endswith(".EXE")
    assert "dl.dell.com" in direct


def test_download_driver_package_resolves_dell_page() -> None:
    offer = {
        "source": "oem",
        "download_kind": "url",
        "title": "Realtek PCIe Ethernet Controller Driver",
        "url": "https://www.dell.com/support/home/us/en/19/Drivers/DriversDetails?driverId=GD26K",
    }
    direct = (
        "https://dl.dell.com/FOLDER14305413M/1/"
        "Realtek-PCIe-Ethernet-Controller-Driver_GD26K_WIN64_1168.28.1224.2025_A03.EXE"
    )
    with mock.patch.object(
        dc,
        "resolve_vendor_package_download_url",
        return_value=(True, "", direct),
    ), mock.patch.object(
        # download_driver_package_for_install calls this as a module-level name; patching
        # the driver_catalog re-export let the test attempt a real dl.dell.com download.
        cdl,
        "download_file_to_folder",
        return_value=(True, "saved", r"C:\Downloads\BSODAnalyzer_drivers\pkg.exe"),
    ) as mock_dl:
        ok, msg, path = dc.download_driver_package_for_install(offer)
    assert ok
    assert path
    mock_dl.assert_called_once()
    assert mock_dl.call_args[0][0] == direct


def test_get_dell_oem_rows_local_dup_fallback() -> None:
    dc.clear_oem_cache()
    dc.configure_catalog(oem_session_cache=True)
    rows = [
        {
            "title": "Realtek PCIe Ethernet Controller Driver",
            "version": "1168.28.1224.2025",
            "date": "2026-05-11",
            "url": "https://example.test/nic",
            "category": "Network",
        }
    ]
    with mock.patch.object(dc, "_get_dell_oem_rows_from_api", return_value=[]):
        with mock.patch.object(dc, "_get_dell_oem_rows_from_local_dup", return_value=rows):
            got, fallback = dc.get_dell_oem_rows({"system_manufacturer": "Alienware"})
    assert len(got) == 1
    assert got[0]["version"] == "1168.28.1224.2025"
    assert "dell.com" in fallback


def test_machine_fingerprint_includes_service_tag() -> None:
    import catalog_cache as ccat

    ctx = {
        "system_manufacturer": "Dell Inc.",
        "system_model": "Alienware m17 R5 AMD",
        "service_tag": "DZ6R1Q3",
    }
    fp = ccat.machine_fingerprint(ctx)
    assert "tag:dz6r1q3" in fp


def test_cache_rejects_wrong_machine_on_load() -> None:
    import catalog_cache as ccat

    blob = {"machine": "dell inc.|alienware m17|tag:aaaaaaa", "offers": [{"title": "x"}]}
    ctx = {"system_manufacturer": "Dell Inc.", "system_model": "Alienware m17", "service_tag": "DZ6R1Q3"}
    assert ccat.cache_matches_machine(blob, ctx) is False
    with mock.patch.object(ccat, "_read_json", return_value=blob):
        offers, loaded = ccat.load_oem_offers(ctx)
    assert loaded is None
    assert offers == []


def test_is_catalog_stale_when_only_one_blob() -> None:
    import catalog_cache as ccat

    wu = {"cached_at": "2026-01-01T00:00:00Z", "rows": [{}]}
    with mock.patch.object(ccat, "_read_json", side_effect=lambda name: wu if name == ccat._WU_FILE else None):
        with mock.patch.object(ccat, "is_catalog_fresh", return_value=True):
            with mock.patch.object(ccat.app_set, "allows_catalog_disk_cache", return_value=True):
                assert ccat.is_catalog_stale() is False


def test_amd_vendor_cache_key_per_gpu() -> None:
    chipset = dc._amd_vendor_cache_key({"hw_category": "chipset", "vendor_key": "amd"})
    igpu = dc._amd_vendor_cache_key({
        "hw_category": "display",
        "vendor_key": "amd",
        "instance_id": "PCI\\VEN_1002&DEV_1681&SUBSYS_0B5B1028",
    })
    dgpu = dc._amd_vendor_cache_key({
        "hw_category": "display",
        "vendor_key": "amd",
        "instance_id": "PCI\\VEN_1002&DEV_73EF&SUBSYS_0B5B1028",
    })
    assert chipset == "amd:chipset"
    assert igpu != dgpu
    assert "1681" in igpu
    assert "73ef" in dgpu


def test_nvidia_vendor_cache_key_matches_fetch() -> None:
    ctx = {
        "vendor_key": "nvidia",
        "video_controllers": [{"pnp_device_id": "PCI\\VEN_10DE&DEV_25A0&SUBSYS_0B5B1028"}],
    }
    pnp = dc._nvidia_pnp_id_from_ctx(ctx)
    key = dc._nvidia_vendor_cache_key(ctx)
    assert "VEN_10DE" in pnp
    assert key.startswith("nvidia:")
    assert urllib.parse.quote(pnp, safe="") in key


def test_fetch_live_oem_msi_via_baseboard() -> None:
    ctx = {"device_label": "Ethernet", "vendor_key": "realtek", "pnp_class": "net"}
    system = {"system_manufacturer": "Micro-Star International Co., Ltd.", "baseboard_manufacturer": "MSI"}
    with mock.patch.object(dc, "fetch_msi_oem_offers", return_value=[{"source": "oem", "title": "NIC"}]) as msi:
        with mock.patch.object(dc, "fetch_dell_oem_offers", return_value=[]):
            with mock.patch.object(dc, "fetch_lenovo_oem_offers", return_value=[]):
                with mock.patch.object(dc, "fetch_hp_oem_offers", return_value=[]):
                    with mock.patch.object(dc, "fetch_asus_oem_offers", return_value=[]):
                        with mock.patch.object(dc, "fetch_gigabyte_oem_offers", return_value=[]):
                            with mock.patch.object(dc, "fetch_acer_oem_offers", return_value=[]):
                                got = dc._fetch_live_oem_offers(ctx, system)
    msi.assert_called_once()
    assert got[0]["title"] == "NIC"


def test_persist_session_uses_warmed_oem_cache() -> None:
    import catalog_cache as ccat

    dc.clear_oem_cache()
    dc.configure_catalog(oem_session_cache=True)
    calls = {"n": 0}

    def fetch_rows(_sys: dict | None) -> tuple[list[dict], str]:
        calls["n"] += 1
        return (
            [{"title": "NIC Driver", "version": "2.0", "url": "https://hp.test"}],
            "https://hp.test",
        )

    sys_ctx = {"system_manufacturer": "HP", "system_model": "test"}
    dc._cached_oem_rows("hp", fetch_rows, sys_ctx)
    saved: list[dict] = []
    with mock.patch.object(ccat, "save_oem_offers", side_effect=lambda offers, **kw: saved.extend(offers)):
        with mock.patch.object(dc, "fetch_oem_catalog_for_system") as deep:
            dc.persist_session_catalog_cache(sys_ctx)
            deep.assert_not_called()
    assert calls["n"] == 1
    assert saved and saved[0]["title"] == "NIC Driver"


def test_is_catalog_stale_rejects_wrong_machine() -> None:
    import catalog_cache as ccat

    wu = {
        "cached_at": "2026-01-01T00:00:00Z",
        "machine": "dell inc.|alienware m17|tag:aaaaaaa",
        "rows": [{}],
    }
    oem = {
        "cached_at": "2026-01-01T00:00:00Z",
        "machine": "dell inc.|alienware m17|tag:aaaaaaa",
        "offers": [{}],
    }
    ctx = {
        "system_manufacturer": "Dell Inc.",
        "system_model": "Alienware m17",
        "service_tag": "DZ6R1Q3",
    }

    def _read(name: str):
        if name == ccat._WU_FILE:
            return wu
        if name == ccat._OEM_FILE:
            return oem
        return None

    with mock.patch.object(ccat, "_read_json", side_effect=_read):
        with mock.patch.object(ccat, "is_catalog_fresh", return_value=True):
            with mock.patch.object(ccat.app_set, "allows_catalog_disk_cache", return_value=True):
                assert ccat.is_catalog_stale(system_ctx=ctx) is True


def test_chipset_context_includes_pnp_anchor() -> None:
    inv = [
        {
            "name": "PCI\\VEN_1022&DEV_15B8&SUBSYS_10281028",
            "display_name": "AMD SMBus Controller",
            "version": "1.0",
        }
    ]
    ctx = dc._build_chipset_catalog_context("amd", "AMD Chipset", "8.0", inv, None)
    assert "VEN_1022" in ctx.get("instance_id", "")
    assert ctx.get("pci_tokens")


def test_score_update_match_no_duplicate_vendor_bonus() -> None:
    ctx = {"vendor_key": "nvidia", "device_label": "GPU", "pnp_class": "display"}
    score = dc._score_update_match("NVIDIA display driver", ctx)
    assert score == 16


def test_nvidia_ctx_eligible_without_vendor_key() -> None:
    ctx = {
        "pnp_class": "display",
        "device_label": "NVIDIA GeForce RTX 4080",
        "vendor_key": "",
    }
    assert dc._nvidia_ctx_eligible(ctx)


def test_fetch_nvidia_uses_primary_lookup() -> None:
    ctx = {
        "pnp_class": "display",
        "device_label": "NVIDIA GeForce RTX 4080",
        "video_controllers": [{"pnp_device_id": "PCI\\VEN_10DE&DEV_2782"}],
    }
    ajax_di = {
        "Version": "610.62",
        "ReleaseDateTime": "Tue Jun 16, 2026",
        "NameLocalized": "GeForce Game Ready Driver",
        "DownloadURL": "https://example.test/driver.exe",
        "ID": "272764",
    }
    with mock.patch.object(
        dc, "_nvidia_lookup_download_info", return_value=(ajax_di, "ajax_grd")
    ):
        offers = dc.fetch_nvidia_driver_offer(ctx)
    versioned = [o for o in offers if (o.get("version") or "").strip()]
    assert versioned
    assert versioned[-1]["version"] == "610.62"
    assert versioned[-1]["date"] == "2026-06-16"


def test_nvidia_processfind_html_parser() -> None:
    html = """
    <tr id="driverList">
      <td class="version">610.62</td>
      <td class="date">Jun 16, 2026</td>
    </tr>
    """
    parsed = dc._nvidia_parse_processfind_html(html)
    assert parsed is not None
    assert parsed["Version"] == "610.62"


def test_nvidia_lookup_records_fallback_chain() -> None:
    import vendor_fetch as vf

    vf._LAST_FETCH_DIAG.pop("nvidia", None)
    ctx = {"pnp_class": "display", "device_label": "NVIDIA GPU"}
    settings = {"nvidia_html_lookup_fallback": True}
    with mock.patch.object(dc, "_nvidia_fetch_ajax_driver_lookup", return_value=None):
        with mock.patch.object(dc, "_nvidia_fetch_ajax_alternate_os", return_value=None):
            with mock.patch.object(
                dc,
                "_nvidia_fetch_processfind_lookup",
                return_value={"Version": "610.47", "ReleaseDateTime": ""},
            ):
                hit, method = dc._nvidia_lookup_download_info(ctx, settings=settings)
    assert hit is not None
    assert hit["Version"] == "610.47"
    assert method == "processfind_html"
    diag = vf.last_fetch_diag("nvidia")
    assert diag is not None
    assert "ajax_grd: no data" in diag.failures


def test_nvidia_lookup_skips_html_fallback_by_default() -> None:
    ctx = {"pnp_class": "display", "device_label": "NVIDIA GPU"}
    with mock.patch.object(dc, "_nvidia_fetch_ajax_driver_lookup", return_value=None):
        with mock.patch.object(dc, "_nvidia_fetch_ajax_alternate_os", return_value=None):
            with mock.patch.object(
                dc, "_nvidia_fetch_processfind_lookup"
            ) as processfind:
                hit, method = dc._nvidia_lookup_download_info(
                    ctx, settings={"nvidia_html_lookup_fallback": False}
                )
    processfind.assert_not_called()
    assert hit is None
    assert method == ""


def test_amd_scrape_js_fallback_step() -> None:
    html = (
        '<script id="__NEXT_DATA__">{"props":{"pageProps":{"x":'
        '"26.10/amd-software-adrenalin-edition-26.6.1-minimalsetup.exe"}}}</script>'
    )
    with mock.patch.object(dc, "_amd_fetch_from_download_page", return_value=None):
        with mock.patch.object(
            dc, "_amd_fetch_download_page_rendered", return_value=("26.6.1", "")
        ):
            ver, _ = dc._scrape_amd_driver_version(
                {"hw_category": "graphics", "device_label": "AMD Radeon RX 7900"}
            )
    assert ver == "26.6.1"


def test_amd_scrape_uses_download_center() -> None:
    html = (
        '<script id="__NEXT_DATA__">{"props":{"pageProps":{"x":'
        '"26.10/amd-software-adrenalin-edition-26.6.1-minimalsetup.exe"}}}</script>'
    )
    with mock.patch.object(dc, "_amd_graphics_product_url", return_value=None):
        with mock.patch.object(dc, "_amd_fetch_from_product_leaf", return_value=None):
            with mock.patch.object(dc, "_amd_http_get_robust", return_value=(True, html)):
                ver, _ = dc._scrape_amd_driver_version(
                    {"hw_category": "graphics", "device_label": "AMD Radeon"}
                )
    assert ver == "26.6.1"


def test_amd_chipset_scrape_from_hub_leaf_pages() -> None:
    hub_html = (
        "https://www.amd.com/en/support/downloads/drivers.html/chipsets/am5/b650.html"
    )
    leaf_html = "AMD Chipset Drivers WHQL 8.05.04.516 for Windows"
    with mock.patch.object(dc, "_amd_fetch_from_download_page", return_value=None):
        with mock.patch.object(dc, "_amd_fetch_download_page_rendered", return_value=None):
            # The hub is fetched with _amd_http_get_robust, and the leaf pages with
            # catalog_amd_fetch's own _amd_fetch_page_html — patching _http_get and the
            # driver_catalog re-export left this test scraping amd.com for real.
            with mock.patch.object(dc, "_amd_http_get_robust", return_value=(True, hub_html)):
                with mock.patch.object(
                    caf, "_amd_fetch_page_html", return_value=(True, leaf_html)
                ):
                    ver, _ = dc._scrape_amd_driver_version(
                        {"hw_category": "chipset", "device_label": "AMD Chipset"}
                    )
    assert ver == "8.05.04.516"


def test_amd_chipset_leaf_urls_unescape_hub_json() -> None:
    hub = (
        "&#34;url&#34;:&#34;https://www.amd.com/en/support/downloads/drivers.html/"
        "chipsets/am5/x870.html&#34;"
    )
    urls = dc._amd_chipset_leaf_urls(hub)
    assert urls == [
        "https://www.amd.com/en/support/downloads/drivers.html/chipsets/am5/x870.html"
    ]


def test_intel_scrape_dsa_fallback() -> None:
    with mock.patch.object(dc, "_intel_fetch_product_page", return_value=None):
        with mock.patch.object(
            dc,
            "_intel_fetch_dsa_graphics_page",
            return_value=("32.0.101.8826", "", dc._INTEL_DSA_URL, ""),
        ):
            ver, _date, url, _direct = dc._scrape_intel_driver_version("graphics")
    assert ver == "32.0.101.8826"
    assert "785597" in url


def test_intel_chipset_scrape_dsa_fallback() -> None:
    with mock.patch.object(dc, "_intel_fetch_product_page", return_value=None):
        with mock.patch.object(
            dc,
            "_intel_fetch_dsa_chipset_page",
            return_value=("10.1.20000.1234", "", dc._INTEL_DSA_URL, ""),
        ):
            ver, _date, url, _direct = dc._scrape_intel_driver_version("chipset")
    assert ver.startswith("10.")
    assert "785597" in url


def test_nvidia_branch_vs_internal_compare_by_date() -> None:
    status, _note = dc.compare_driver_to_installed(
        "581.42",
        "32.0.15.8100",
        installed_date="2024-01-15",
        candidate_date="2026-06-16",
        source="vendor",
    )
    assert status == "newer"


def test_nvidia_internal_installed_uses_branch_from_programs() -> None:
    with mock.patch.object(dc, "_load_nvidia_branch_installed_version", return_value="610.74"):
        status, note = dc.compare_driver_to_installed(
            "32.0.16.1074",
            "610.74",
            installed_date="2024-01-15",
            candidate_date="2026-07-07",
            source="vendor",
        )
    assert status == "same"
    assert "610.74" in note


def test_nvidia_internal_installed_uses_windows_display_version() -> None:
    with mock.patch.object(dc, "_load_nvidia_branch_installed_version", return_value=""):
        status, note = dc.compare_driver_to_installed(
            "32.0.16.1074",
            "610.74",
            installed_date="2024-01-15",
            candidate_date="2026-07-07",
            candidate_windows_version="32.0.16.1074",
            source="vendor",
        )
    assert status == "same"
    assert "1074" in note


def test_clear_installed_package_versions_cache() -> None:
    import catalog_installed_packages as inst_pkg

    inst_pkg._INSTALLED_PACKAGE_VERSIONS_CACHE = {"nvidia_branch": "581.42"}
    dc.clear_installed_package_versions_cache()
    assert inst_pkg._INSTALLED_PACKAGE_VERSIONS_CACHE is None


def test_nvidia_branch_versions_compare_normally() -> None:
    status, _note = dc.compare_driver_to_installed(
        "581.42",
        "610.62",
        installed_date="2025-01-10",
        candidate_date="2026-06-16",
        source="vendor",
    )
    assert status == "newer"


def test_nvidia_psid_pfid_gtx_1060_from_pci_dev() -> None:
    ctx = {
        "device_label": "NVIDIA GeForce GTX 1060",
        "instance_id": "PCI\\VEN_10DE&DEV_1C60&SUBSYS_15801043&REV_A1\\4&1C84857B&0&0008",
        "video_controllers": [{"pnp_device_id": "PCI\\VEN_10DE&DEV_1C60&SUBSYS_15801043"}],
    }
    psid, pfid = dc._nvidia_psid_pfid_from_ctx(ctx)
    assert (psid, pfid) == ("101", "817")
    assert dc._nvidia_pci_dev_from_ctx(ctx) == "1C60"


def test_nvidia_ajax_rejects_rtx610_on_gtx1060() -> None:
    ctx = {"device_label": "NVIDIA GeForce GTX 1060", "pnp_class": "display"}
    bad = {
        "Version": "610.88",
        "NameLocalized": "NVIDIA%20RTX%20Driver%20Release%20580",
    }
    good = {
        "Version": "582.66",
        "NameLocalized": "GeForce%20Security%20Update%20Driver",
    }
    assert not dc._nvidia_ajax_result_plausible(bad, ctx)
    assert dc._nvidia_ajax_result_plausible(good, ctx)


def test_intel_hint_skips_graphics_on_sata_ahci() -> None:
    ctx = {
        "vendor_key": "intel",
        "device_label": "Intel(R) 100 Series/C230 Chipset Family SATA AHCI Controller",
        "pnp_class": "SCSIAdapter",
    }
    assert dc._intel_driver_hint_from_ctx(ctx) == "chipset"
    with mock.patch.object(dc, "_scrape_intel_driver_version", return_value=("", "", "", "")):
        offers = dc.fetch_intel_driver_offers(ctx)
    assert all("32.0.101" not in (o.get("version") or "") for o in offers)


def test_intel_fetch_empty_on_non_driver_intel_row() -> None:
    ctx = {
        "vendor_key": "intel",
        "device_label": "Intel(R) USB 3.0 eXtensible Host Controller - 1.0 (Microsoft)",
        "pnp_class": "USB",
    }
    assert dc._intel_driver_hint_from_ctx(ctx) is None
    assert dc.fetch_intel_driver_offers(ctx) == []


def test_nvidia_ctx_ineligible_for_hd_audio() -> None:
    ctx = {
        "pnp_class": "media",
        "device_label": "NVIDIA High Definition Audio",
        "vendor_key": "nvidia",
        "primary_version": "1.4.5.7",
    }
    assert not dc._nvidia_ctx_eligible(ctx)
    assert dc.fetch_nvidia_driver_offer(ctx) == []


def test_oem_rejects_amd_gpu_on_nvidia_display() -> None:
    row = {
        "title": "AMD Radeon RX 6700M/6850M XT Graphics Driver",
        "version": "32.0.11029.1008",
    }
    ctx = {
        "pnp_class": "display",
        "device_label": "NVIDIA GeForce RTX 3070 Ti Laptop GPU",
        "vendor_key": "nvidia",
        "primary_version": "32.0.16.1047",
    }
    assert dc._reject_vendor_driver_class_mismatch(row, ctx) == "cross_vendor_gpu_offer"
    assert not dc._oem_row_eligible_for_ctx(row, ctx)


def test_oem_rejects_realtek_hd_on_amd_audio_coprocessor() -> None:
    row = {
        "source": "oem",
        "title": "Realtek High Definition Audio Driver",
        "version": "6.0.9738.1",
        "category": "Audio",
    }
    ctx = {
        "pnp_class": "system",
        "device_label": "AMD Audio CoProcessor",
        "vendor_key": "amd",
        "primary_version": "6.0.2.118",
    }
    assert dc._reject_oem_audio_vendor_mismatch(row, ctx) == "oem_audio_vendor_mismatch"
    assert dc._filter_offers_for_device_ctx([row], ctx, min_oem_score=2) == []


def test_possible_coverage_gap_when_installed_beats_catalog() -> None:
    assert dc.possible_coverage_gap("6.0.9929.1", [], status="none")
    offers = dc.enrich_offers_with_comparison(
        [{"source": "oem", "title": "Stale", "version": "6.0.9738.1"}],
        "6.0.9929.1",
    )
    assert dc.possible_coverage_gap("6.0.9929.1", offers, status="none")


def test_possible_coverage_gap_false_when_status_newer() -> None:
    offers = dc.enrich_offers_with_comparison(
        # A newer version alone reports "uncertain" without a fetchable package — see
        # test_has_actionable_versioned_offer_skips_support_link — so give it a real one.
        [{
            "source": "oem",
            "title": "NIC",
            "version": "1168.28.1224.2025",
            "url": "https://dl.dell.com/FOLDER/Network_Driver.EXE",
        }],
        "1125.28.1224.2025",
    )
    assert dc.summarize_offer_status(offers) == "newer"
    assert not dc.possible_coverage_gap(
        "1125.28.1224.2025", offers, status="newer"
    )


def test_possible_coverage_gap_not_inverted_when_catalog_is_newer() -> None:
    assert not dc.possible_coverage_gap(
        "2.2.0.137",
        [{"source": "vendor", "title": "AMD chipset", "version": "8.05.04.516"}],
        status="uncertain",
    )


def test_possible_coverage_gap_false_when_cross_scheme_match() -> None:
    offers = dc.enrich_offers_with_comparison(
        [{
            "source": "vendor",
            "source_label": "Manufacturer (Realtek)",
            "title": "Install_PCIE_Win11.zip",
            "version": "11.030.50",
        }],
        "1125.30.50.508",
        device_ctx={
            "vendor_key": "realtek",
            "pnp_class": "net",
            "device_label": "Realtek Gaming 2.5GbE Family Controller",
        },
    )
    assert offers[0]["vs_installed"] == "same"
    assert not dc.possible_coverage_gap(
        "1125.30.50.508",
        offers,
        status="uncertain",
        device_ctx={"vendor_key": "realtek", "pnp_class": "net"},
    )


def test_prioritize_mscatalog_scored_rows_keeps_strict_match() -> None:
    ctx = {
        "instance_id": (
            "HDAUDIO\\FUNC_01&VEN_10EC&DEV_0295&SUBSYS_10280B5B&REV_1000\\5&35e90671&0&0001"
        ),
        "primary_version": "6.0.9998.1",
    }
    wrong = (
        30,
        {
            "title": "Other Driver (9.9.9.9)",
            "version": "9.9.9.9",
            "update_id": "wrong-id",
            "products": "INTELAUDIO\\DEV_0245",
        },
        True,
    )
    good = (
        25,
        {
            "title": "Good Driver (6.0.9998.1)",
            "version": "6.0.9998.1",
            "update_id": "good-id",
            "products": "HDAUDIO\\FUNC_01&VEN_10EC&DEV_0295&SUBSYS_10280B5B",
        },
        True,
    )
    out = dc._prioritize_mscatalog_scored_rows([wrong, good], ctx)
    assert out[0][1]["version"] == "6.0.9998.1"


def test_amd_component_vs_chipset_suite_compare_uncertain() -> None:
    vs, note = dc.compare_driver_to_installed("2.2.0.137", "8.05.04.516")
    assert vs == "uncertain"
    assert "chipset" in note.lower()


def test_amd_smbus_matches_chipset_plumbing() -> None:
    assert dc._device_is_amd_chipset_plumbing({"device_label": "amd smbus"})


def test_oem_rejects_amd_chipset_on_smbus() -> None:
    row = {
        "source": "oem",
        "title": "AMD Chipset Driver",
        "version": "7.12.30.210",
    }
    ctx = {
        "pnp_class": "system",
        "device_label": "AMD SMBUS",
        "vendor_key": "amd",
        "primary_version": "2.0.0.26",
    }
    assert dc._reject_oem_amd_chipset_on_component_inf(row, ctx)


def test_oem_rejects_realtek_ethernet_on_universal_service() -> None:
    row = {
        "source": "oem",
        "title": "Realtek PCIe Ethernet Controller Driver",
        "version": "1168.28.1224.2025",
        "category": "Network",
    }
    ctx = {
        "pnp_class": "media",
        "device_label": "Realtek Audio Universal Service",
        "vendor_key": "realtek",
        "primary_version": "6.0.9929.1",
    }
    assert dc._reject_realtek_catalog_row(row, ctx) == "realtek_net_on_swc_device"
    assert dc._filter_offers_for_device_ctx([row], ctx, min_oem_score=2) == []


def test_oem_rejects_realtek_ethernet_on_effects_component_apo() -> None:
    row = {
        "source": "oem",
        "title": "Realtek PCIe Ethernet Controller Driver",
        "version": "1168.28.1224.2025",
        "category": "Network",
    }
    ctx = {
        "pnp_class": "audioprocessingobject",
        "device_label": "Realtek Audio Effects Component",
        "vendor_key": "realtek",
        "primary_version": "13.1020.1391.394",
    }
    assert dc._reject_realtek_catalog_row(row, ctx) == "realtek_net_on_apo_device"
    assert dc._filter_offers_for_device_ctx([row], ctx, min_oem_score=2) == []


def test_realtek_wdm_role_when_media_row_has_6_0_codec_version() -> None:
    ctx = {
        "pnp_class": "media",
        "device_label": "Realtek Audio Effects Component",
        "primary_version": "6.0.9929.1",
    }
    assert dc._realtek_device_component_role(ctx) == "wdm"


def test_summarize_oem_newer_when_vendor_realtek_net_uncertain() -> None:
    offers = dc.enrich_offers_with_comparison(
        [
            {
                "source": "oem",
                "source_label": "OEM (Dell / Alienware)",
                "title": "Realtek PCIe Ethernet Controller Driver",
                "version": "1168.28.1224.2025",
                # Needed for "newer": a versioned offer with no fetchable package is
                # reported as uncertain by the update reporting policy.
                "url": "https://dl.dell.com/FOLDER/Network_Driver.EXE",
            },
            {
                "source": "vendor",
                "source_label": "Manufacturer (Realtek)",
                "title": "Install_PCIE_Win11_11029.zip",
                "version": "11.029.50",
                "date": "2026-04-24",
            },
        ],
        "1125.28.1224.2025",
        device_ctx={
            "pnp_class": "net",
            "device_label": "Realtek Gaming 2.5GbE Family Controller",
            "vendor_key": "realtek",
        },
    )
    assert dc.summarize_offer_status(offers) == "newer"


def test_oem_rejects_amd_chipset_package_on_gpio_component_version() -> None:
    row = {
        "source": "oem",
        "title": "AMD Chipset Driver",
        "version": "7.12.30.210",
        "category": "Chipset",
    }
    ctx = {
        "pnp_class": "system",
        "device_label": "AMD GPIO Controller",
        "vendor_key": "amd",
        "primary_version": "2.2.0.137",
    }
    assert dc._reject_oem_amd_chipset_on_component_inf(row, ctx) == "oem_chipset_package_on_component_inf"
    assert dc._filter_offers_for_device_ctx([row], ctx, min_oem_score=2) == []


def test_oem_accepts_dell_realtek_pcie_on_gaming_2_5gbe() -> None:
    row = {
        "title": "Realtek PCIe Ethernet Controller Driver",
        "version": "1168.28.1224.2025",
        "category": "Network",
    }
    ctx = {
        "pnp_class": "net",
        "device_label": "Realtek Gaming 2.5GbE Family Controller",
        "vendor_key": "realtek",
        "primary_version": "1125.28.1224.2025",
    }
    assert dc._reject_realtek_oem_net_family_mismatch(row, ctx) is None
    assert dc._oem_row_eligible_for_ctx(row, ctx)


def test_oem_accepts_dell_realtek_pcie_after_1125_30_branch() -> None:
    row = {
        "title": "Realtek PCIe Ethernet Controller Driver",
        "version": "1168.28.1224.2025",
        "category": "Network",
    }
    ctx = {
        "pnp_class": "net",
        "device_label": "Realtek Gaming 2.5GbE Family Controller",
        "vendor_key": "realtek",
        "primary_version": "1125.30.50.508",
        "instance_id": (
            "PCI\\VEN_10EC&DEV_8125&SUBSYS_0B5B1028&REV_05\\01000000684CE00000"
        ),
    }
    assert dc._reject_realtek_oem_net_family_mismatch(row, ctx) is None
    out = dc.enrich_offers_with_comparison(
        [{
            "source": "oem",
            "source_label": "OEM (Dell / Alienware)",
            "title": row["title"],
            "version": row["version"],
            "date": "2026-05-11",
        }],
        "1125.30.50.508",
        device_ctx=ctx,
    )
    assert out[0]["vs_installed"] == "uncertain"
    assert "1168" in (out[0].get("compare_note") or "")


def test_realtek_nic_same_oem_family_1125_1168() -> None:
    assert dc._realtek_nic_same_oem_family(
        "1125.28.1224.2025",
        "1168.28.1224.2025",
    )
    assert not dc._realtek_nic_same_oem_family(
        "1125.28.1224.2025",
        "210.2.50.2024",
    )


def test_should_defer_microsoft_when_oem_older_than_installed() -> None:
    offers = [{
        "source": "oem",
        "title": "Realtek High Definition Audio Driver",
        "version": "6.0.9738.1",
        "confidence": "high",
    }]
    assert not dc.should_defer_microsoft_catalog(offers, "6.0.9929.1")
    assert dc.should_defer_microsoft_catalog(offers, "6.0.9600.0")


def test_should_not_defer_microsoft_when_oem_version_incomparable() -> None:
    offers = [{
        "source": "vendor",
        "source_label": "Manufacturer (Realtek)",
        "title": "Realtek PCIe GBE Family Controller",
        "version": "11.029.50",
        "confidence": "medium",
    }]
    assert not dc.should_defer_microsoft_catalog(
        offers,
        "1125.28.1224.2025",
    )


def test_realtek_net_never_defers_microsoft_catalog() -> None:
    offers = [{
        "source": "oem",
        "title": "Realtek Gaming 2.5GbE Family Controller Driver",
        "version": "1168.28.1224.2025",
        "confidence": "high",
    }]
    ctx = {
        "vendor_key": "realtek",
        "pnp_class": "net",
        "device_label": "Realtek Gaming 2.5GbE Family Controller",
    }
    assert not dc.should_defer_microsoft_catalog(
        offers,
        "1125.28.1224.2025",
        ctx,
    )


def test_realtek_audio_mscatalog_not_hwid_verified_without_dev_match() -> None:
    ctx = {
        "vendor_key": "realtek",
        "pnp_class": "media",
        "device_label": "Realtek Audio",
        "primary_version": "6.0.9998.1",
        "instance_id": (
            "HDAUDIO\\FUNC_01&VEN_10EC&DEV_0295&SUBSYS_10280B5B&REV_1000\\5&35e90671&0&0001"
        ),
    }
    row = {
        "source": "microsoft",
        "title": "Realtek Semiconductor Corp. MEDIA Driver Update (6.0.10001.1)",
        "version": "6.0.10001.1",
        "products": "INTELAUDIO\\FUNC_01&VEN_10EC&DEV_0245&SUBSYS_103C8F04",
    }
    assert not dc._catalog_row_hwid_strict_matches_ctx(row, ctx)
    assert not dc._realtek_wdm_mscatalog_trusted(row, ctx)
    out = dc.enrich_offers_with_comparison(
        [row],
        "6.0.9998.1",
        device_ctx=ctx,
    )
    assert out[0]["vs_installed"] == "uncertain"
    assert out[0].get("hwid_matched") is False
    assert "DEV_0295" in (out[0].get("compare_note") or "")


def test_realtek_nic_mscatalog_trusted_same_family() -> None:
    ctx = {
        "vendor_key": "realtek",
        "pnp_class": "net",
        "device_label": "Realtek Gaming 2.5GbE Family Controller",
        "primary_version": "1125.28.1224.2025",
    }
    row = {
        "source": "microsoft",
        "title": "Realtek Net Driver Update (1125.29.50.202)",
        "version": "1125.29.50.202",
    }
    assert dc._realtek_nic_mscatalog_trusted(row, ctx)


def test_realtek_nic_mscatalog_enriched_as_newer_not_uncertain() -> None:
    ctx = {
        "vendor_key": "realtek",
        "pnp_class": "net",
        "device_label": "Realtek Gaming 2.5GbE Family Controller",
        "primary_version": "1125.28.1224.2025",
    }
    offers = [{
        "source": "microsoft",
        "title": "Realtek Net Driver Update (1125.29.50.202)",
        "version": "1125.29.50.202",
        "date": "2026-02-01",
    }]
    out = dc.enrich_offers_with_comparison(
        offers,
        "1125.28.1224.2025",
        device_ctx=ctx,
    )
    assert out[0]["vs_installed"] == "newer"
    assert out[0].get("hwid_matched") is True


def test_realtek_nic_cross_scheme_equivalent_oem_vs_public() -> None:
    assert dc._realtek_nic_cross_scheme_equivalent(
        "1125.30.50.508",
        "11.030.50",
    )
    vs, note = dc.compare_driver_to_installed(
        "1125.30.50.508",
        "11.030.50",
        source="vendor",
    )
    assert vs == "same"
    assert "11.x.y" in note


def test_realtek_wdm_mscatalog_keeps_hwid_verified_over_higher_wrong_dev() -> None:
    ctx = {
        "vendor_key": "realtek",
        "pnp_class": "media",
        "primary_version": "6.0.9998.1",
        "instance_id": (
            "HDAUDIO\\FUNC_01&VEN_10EC&DEV_0295&SUBSYS_10280B5B&REV_1000\\5&35e90671&0&0001"
        ),
    }
    matched = (
        20,
        {
            "title": "Realtek Semiconductor Corp. MEDIA Driver Update (6.0.9998.1)",
            "version": "6.0.9998.1",
            "update_id": "aaaa-bbbb",
            "products": "HDAUDIO\\FUNC_01&VEN_10EC&DEV_0295&SUBSYS_10280B5B",
        },
        True,
    )
    wrong_dev = (
        18,
        {
            "title": "Realtek Semiconductor Corp. MEDIA Driver Update (6.0.10001.1)",
            "version": "6.0.10001.1",
            "update_id": "cccc-dddd",
            "products": "INTELAUDIO\\FUNC_01&VEN_10EC&DEV_0245&SUBSYS_103C8F04",
        },
        True,
    )
    kept = dc._realtek_wdm_mscatalog_codec_rows_to_keep([wrong_dev, matched], ctx)
    versions = [(item[1].get("version") or "") for item in kept]
    assert versions[0] == "6.0.9998.1"
    assert "6.0.9998.1" in versions


def test_should_skip_oem_for_realtek_net_even_with_manufacturer_newer() -> None:
    ctx = {
        "pnp_class": "net",
        "device_label": "Realtek Gaming 2.5GbE Family Controller",
        "vendor_key": "realtek",
        "primary_version": "1125.28.1224.2025",
    }
    mfr = [{
        "source": "vendor",
        "source_label": "Manufacturer (Realtek)",
        "title": "Realtek PCIe GBE Family Controller",
        "version": "11.029.50",
        "confidence": "medium",
        "vs_installed": "older",
    }]
    assert not dc._should_skip_oem_after_manufacturer_tier(ctx, mfr, ctx["primary_version"])


def test_oem_rejects_realtek_on_nvidia_hd_audio() -> None:
    row = {
        "title": "Realtek High Definition Audio Driver",
        "version": "6.0.9738.1",
    }
    ctx = {
        "pnp_class": "media",
        "device_label": "NVIDIA High Definition Audio",
        "vendor_key": "nvidia",
        "primary_version": "1.4.5.7",
    }
    assert dc._reject_oem_audio_vendor_mismatch(row, ctx) == "oem_audio_vendor_mismatch"
    assert not dc._oem_row_eligible_for_ctx(row, ctx)


def test_oem_rejects_dolby_app_on_nvidia_hd_audio() -> None:
    row = {"title": "Dolby Audio Application", "version": "3.17.945.0"}
    ctx = {
        "pnp_class": "media",
        "device_label": "NVIDIA High Definition Audio",
        "vendor_key": "nvidia",
    }
    assert dc._reject_oem_application_on_driver_device(row, ctx) == "oem_application_on_driver_device"
    assert not dc._oem_row_eligible_for_ctx(row, ctx)


def test_oem_rejects_ethernet_on_usb_xhci() -> None:
    row = {"title": "Realtek PCIe Ethernet Controller Driver", "version": "1168.28.1224.2025"}
    ctx = {"pnp_class": "usb", "device_label": "USB xHCI Compliant Host Controller", "vendor_key": ""}
    assert dc._reject_vendor_driver_class_mismatch(row, ctx) == "oem_net_on_usb"


def test_oem_keywords_nvidia_audio_not_gpu() -> None:
    ctx = {
        "pnp_class": "media",
        "device_label": "NVIDIA High Definition Audio",
        "vendor_key": "nvidia",
    }
    kws = dc._oem_search_keywords(ctx)
    assert "audio" in kws
    assert "geforce" not in kws


def test_oem_keywords_nvidia_usbc_not_gpu() -> None:
    ctx = {
        "pnp_class": "usb",
        "device_label": "NVIDIA USBC Driver",
        "vendor_key": "nvidia",
    }
    kws = dc._oem_search_keywords(ctx)
    assert "geforce" not in kws
    assert "gpu" not in kws


def test_shared_rejects_amd_bulk_on_oem_monitor() -> None:
    row = {"title": "AMD System Driver Update (23.19.0.5)", "version": "8.05.04.516"}
    ctx = {
        "pnp_class": "monitor",
        "device_label": "Dell Alienware 17 R5 AMD LGD06E3 Display",
        "vendor_key": "amd",
    }
    assert dc._shared_catalog_row_rejects(row, ctx) == "amd_system_driver_wrong_class"
    assert not dc._oem_row_eligible_for_ctx(row, ctx)


def test_wu_prefilter_rejects_amd_system_on_monitor() -> None:
    rows = [
        {
            "Title": "AMD System Driver Update (23.19.0.5)",
            "Version": "8.05.04.516",
            "HardwareIds": [],
        }
    ]
    ctx = {
        "pnp_class": "monitor",
        "device_label": "Dell Alienware 17 R5 AMD LGD06E3 Display",
        "vendor_key": "amd",
    }
    filtered = dc._prefilter_wu_rows_for_ctx(rows, ctx)
    assert filtered == []


def test_oem_rejects_nvidia_audio_on_realtek_device() -> None:
    row = {"title": "NVIDIA High Definition Audio Driver", "version": "1.4.5.7"}
    ctx = {
        "pnp_class": "media",
        "device_label": "Realtek(R) Audio",
        "vendor_key": "realtek",
    }
    assert dc._reject_oem_audio_vendor_mismatch(row, ctx) == "oem_audio_vendor_mismatch"


def test_reject_oem_on_third_party_ifi_dac() -> None:
    row = {
        "source": "oem",
        "title": "Realtek High Definition Audio Driver",
        "version": "6.0.9738.1",
    }
    ctx = {
        "pnp_class": "media",
        "device_label": "AMR HD+ USB Audio",
        "pnp_manufacturer": "iFi",
        "vendor_key": "ifi",
        "system_manufacturer": "Alienware",
    }
    reason = dc._reject_oem_pc_maker_on_third_party_device(row, ctx)
    assert reason in (
        "oem_pc_maker_on_third_party_device",
        "oem_package_brand_mismatch",
    )
    offers = dc._filter_offers_for_device_ctx([row], ctx)
    assert offers == []


def test_reject_oem_generic_support_on_logitech_mouse() -> None:
    row = {
        "source": "oem",
        "title": "Alienware support — Alienware m17 R5 AMD",
        "url": "https://www.dell.com/support/home",
    }
    ctx = {
        "pnp_class": "usb",
        "device_label": "G900 Chaos Spectrum",
        "pnp_manufacturer": "Logitech",
        "vendor_key": "logitech",
        "system_manufacturer": "Alienware",
    }
    reason = dc._reject_oem_pc_maker_on_third_party_device(row, ctx)
    assert reason in (
        "oem_generic_support_on_third_party",
        "oem_pc_maker_on_third_party_device",
        "oem_package_brand_mismatch",
    )
    offers = dc._filter_offers_for_device_ctx([row], ctx)
    assert offers == []


def test_oem_realtek_still_allowed_on_builtin_realtek_audio() -> None:
    row = {
        "source": "oem",
        "title": "Realtek High Definition Audio Driver",
        "version": "6.0.9738.1",
    }
    ctx = {
        "pnp_class": "media",
        "device_label": "Realtek Audio",
        "pnp_manufacturer": "Realtek",
        "vendor_key": "realtek",
        "system_manufacturer": "Alienware",
    }
    assert dc._pc_oem_catalog_may_target_device(ctx) is True
    assert dc._reject_oem_pc_maker_on_third_party_device(row, ctx) is None
    assert dc._pnp_manufacturer_is_third_party(ctx) is False


def test_dell_technologies_not_logitech_vendor() -> None:
    import bsod_hardware_wmi as hw

    assert hw._extract_vendor_from_string("Dell Technologies") == "dell"


def test_reject_alienware_command_center_on_dbutildrv2() -> None:
    row = {
        "source": "oem",
        "title": (
            "Alienware Command Center 6.x - Full Installer for "
            "Alienware/Dell G Series System"
        ),
        "version": "6.14.20.0",
    }
    ctx = {
        "pnp_class": "DELLUTILS",
        "device_label": "DBUtilDrv2 Device",
        "pnp_manufacturer": "Dell Technologies",
        "vendor_key": "dell",
    }
    assert dc._reject_oem_pc_maker_update_application(row, ctx) == (
        "oem_update_app_on_dell_internal_driver"
    )
    assert dc._filter_offers_for_device_ctx([row], ctx) == []


def test_reject_lg_swc_wu_offer_on_monitor_not_child() -> None:
    row = {
        "source": "microsoft",
        "title": "LG Electronics Inc. SoftwareComponent Driver Update (2.0.2026.810)",
        "version": "2.0.2026.810",
    }
    monitor_ctx = {
        "pnp_class": "MONITOR",
        "device_label": "LG ULTRAGEAR(DisplayPort)",
        "pnp_manufacturer": "LG",
        "vendor_key": "lg",
    }
    swc_ctx = {
        "pnp_class": "SOFTWARECOMPONENT",
        "device_label": "LG Monitor Support Application",
        "pnp_manufacturer": "LG Electronics Inc.",
        "vendor_key": "lg",
    }
    assert dc._reject_vendor_driver_class_mismatch(row, monitor_ctx) == (
        "swc_driver_update_on_monitor"
    )
    assert dc._filter_offers_for_device_ctx([row], monitor_ctx) == []
    assert dc._reject_vendor_driver_class_mismatch(row, swc_ctx) is None


def test_reject_lg_swc_wu_on_amd_opencl_not_lg_child() -> None:
    row = {
        "source": "microsoft",
        "title": "LG Electronics Inc. SoftwareComponent Driver Update (2.0.2026.810)",
        "version": "2.0.2026.810",
    }
    amd_swc_ctx = {
        "pnp_class": "SOFTWARECOMPONENT",
        "device_label": "AMD-OpenCL User Mode Driver",
        "pnp_manufacturer": "Advanced Micro Devices, Inc.",
        "vendor_key": "amd",
        "catalog_role": "softwarecomponent",
    }
    lg_swc_ctx = {
        "pnp_class": "SOFTWARECOMPONENT",
        "device_label": "LG Monitor Support Application",
        "pnp_manufacturer": "LG Electronics Inc.",
        "vendor_key": "lg",
        "catalog_role": "softwarecomponent",
    }
    assert dc._reject_vendor_driver_class_mismatch(row, amd_swc_ctx) == (
        "swc_branded_vendor_mismatch"
    )
    assert dc._filter_offers_for_device_ctx([row], amd_swc_ctx) == []
    assert dc._reject_vendor_driver_class_mismatch(row, lg_swc_ctx) is None


def test_reject_dell_update_app_on_dbutildrv2() -> None:
    row = {
        "source": "oem",
        "title": "Dell Update/Alienware Update Application",
        "version": "4.6.0",
    }
    ctx = {
        "pnp_class": "DELLUTILS",
        "device_label": "DBUtilDrv2 Device",
        "pnp_manufacturer": "Dell Technologies",
        "vendor_key": "dell",
    }
    assert dc._reject_oem_pc_maker_update_application(row, ctx) == (
        "oem_update_app_on_dell_internal_driver"
    )
    assert dc._filter_offers_for_device_ctx([row], ctx) == []


def test_reject_dell_update_app_on_dell_instrumentation() -> None:
    row = {
        "source": "oem",
        "title": "Dell/Alienware Update Windows Universal Application",
        "version": "5.5.0",
    }
    ctx = {
        "pnp_class": "DELLINSTRUMENTATION",
        "device_label": "DellInstrumentation Device",
        "pnp_manufacturer": "Dell Technologies",
        "vendor_key": "dell",
    }
    assert dc._reject_oem_pc_maker_update_application(row, ctx) == (
        "oem_update_app_on_dell_internal_driver"
    )
    assert dc._filter_offers_for_device_ctx([row], ctx) == []


def test_reject_realtek_console_on_asio_component() -> None:
    row = {
        "source": "oem",
        "title": "Realtek Audio Console Application",
        "version": "1.50.322.0",
    }
    ctx = {
        "pnp_class": "SOFTWARECOMPONENT",
        "device_label": "Realtek Asio Component",
        "pnp_manufacturer": "Realtek",
        "vendor_key": "realtek",
    }
    assert dc._reject_realtek_catalog_row(row, ctx) == "realtek_swc_role_mismatch"
    assert dc._filter_offers_for_device_ctx([row], ctx) == []


def test_reject_oem_on_unknown_usb_dac_brand() -> None:
    """Any distinct USB manufacturer — not only iFi/Logitech — is out of OEM scope."""
    row = {
        "source": "oem",
        "title": "Realtek High Definition Audio Driver",
        "version": "6.0.9738.1",
    }
    ctx = {
        "pnp_class": "media",
        "device_label": "K11 — USB Audio",
        "pnp_manufacturer": "FiiO",
        "vendor_key": "fiio",
        "instance_id": "USB\\VID_1852&PID_7022\\...",
        "system_manufacturer": "Alienware",
    }
    assert dc._pc_oem_catalog_may_target_device(ctx) is False
    assert dc._reject_oem_package_brand_mismatch(row, ctx) == "oem_package_brand_mismatch"
    assert dc._filter_offers_for_device_ctx([row], ctx) == []


def test_standard_usb_hid_does_not_receive_pc_oem_versioned_packages() -> None:
    row = {
        "source": "oem",
        "title": "Realtek High Definition Audio Driver",
        "version": "6.0.9738.1",
    }
    ctx = {
        "pnp_class": "hidclass",
        "device_label": "USB Input Device",
        "pnp_manufacturer": "(Standard system devices)",
        "instance_id": "USB\\VID_046D&PID_C539\\...",
        "system_manufacturer": "Alienware",
    }
    assert dc._pc_oem_catalog_may_target_device(ctx) is False
    assert dc._filter_offers_for_device_ctx([row], ctx) == []


def test_filter_offers_uses_shared_rejects_for_oem() -> None:
    offers = [
        {
            "source": "oem",
            "title": "Dolby Audio Application",
            "version": "3.17.945.0",
        }
    ]
    ctx = {
        "pnp_class": "media",
        "device_label": "NVIDIA High Definition Audio",
        "vendor_key": "nvidia",
    }
    assert dc._filter_offers_for_device_ctx(offers, ctx) == []


def test_reject_oem_radio_chip_mismatch_on_generic_bluetooth() -> None:
    row = {
        "source": "oem",
        "title": "MediaTek MT7921 Wi-Fi UWD Driver",
        "version": "3.3.0.540",
    }
    ctx = {
        "pnp_class": "net",
        "device_label": "Microsoft — Bluetooth Device (Personal Area Network)",
        "vendor_key": "microsoft",
    }
    assert dc._reject_oem_radio_chip_mismatch(row, ctx) == "oem_radio_wifi_bt_mismatch"
    assert dc._shared_catalog_row_rejects(row, ctx) == "oem_radio_wifi_bt_mismatch"


def test_mediatek_mt7921_oem_not_rejected_for_chip_label() -> None:
    row = {
        "source": "oem",
        "title": "MediaTek MT7921/MT7922 Wi-Fi UWD Driver",
        "version": "3.3.3.760",
        "category": "Network",
    }
    ctx = {
        "pnp_class": "net",
        "device_label": "MediaTek Wi-Fi 6 MT7921 Wireless LAN Card",
        "vendor_key": "mediatek",
        "instance_id": r"PCI\VEN_14C3&DEV_7961&SUBSYS_E0B7105B&REV_00\4&1CDAF9ED&0&0011",
    }
    assert dc._reject_oem_radio_chip_mismatch(row, ctx) is None
    assert dc._oem_row_eligible_for_ctx(row, ctx)


def test_mediatek_batch_mscatalog_includes_name_fallbacks() -> None:
    ctx = {
        "device_label": "MediaTek Wi-Fi 6 MT7921 Wireless LAN Card",
        "instance_id": r"PCI\VEN_14C3&DEV_7961&SUBSYS_E0B7105B&REV_00\4&1CDAF9ED&0&0011",
        "pnp_class": "Net",
        "vendor_key": "mediatek",
        "_batch_driver_check": True,
    }
    base = dc._catalog_search_queries_for_ctx(ctx)
    batch = dc._batch_mscatalog_queries_for_ctx(ctx, base)
    assert any("MediaTek, Inc. Driver Update" in q for q in batch)
    assert any("MT7921" in q for q in batch)
    assert len(batch) <= 4


def test_reject_wifi_oem_on_mediatek_bluetooth_adapter() -> None:
    row = {
        "source": "oem",
        "title": "MediaTek MT7921 Wi-Fi UWD Driver",
        "version": "3.3.0.540",
    }
    ctx = {
        "pnp_class": "Bluetooth",
        "device_label": "MediaTek Bluetooth Adapter",
        "vendor_key": "mediatek",
    }
    assert dc._reject_oem_radio_chip_mismatch(row, ctx) == "oem_radio_wifi_bt_mismatch"


def test_reject_bluetooth_oem_on_mediatek_wifi_card() -> None:
    row = {
        "source": "oem",
        "title": "MediaTek MT7922/MT7921 Bluetooth UWD Driver",
        "version": "1.930.3.287",
    }
    ctx = {
        "pnp_class": "Net",
        "device_label": "MediaTek Wi-Fi 6 MT7921 Wireless LAN Card",
        "vendor_key": "mediatek",
    }
    assert dc._reject_oem_radio_chip_mismatch(row, ctx) == "oem_radio_wifi_bt_mismatch"


def test_mediatek_wifi_skips_amd_adrenalin_compare_gate() -> None:
    ctx = {
        "vendor_key": "mediatek",
        "pnp_class": "Net",
        "primary_version": "3.5.0.1392",
    }
    vs, note = dc.compare_driver_to_installed(
        "3.5.0.1392",
        "26.30.3.64",
        source="microsoft",
        device_ctx=ctx,
    )
    assert "AMD Adrenalin" not in note
    assert vs in ("older", "newer", "same", "unknown", "uncertain")


def test_reject_mediatek_mscatalog_adrenalin_shaped_rows() -> None:
    row = {
        "source": "microsoft",
        "title": "MediaTek, Inc. Net Driver Update (26.30.3.64)",
        "version": "26.30.3.64",
    }
    ctx = {
        "vendor_key": "mediatek",
        "pnp_class": "Net",
        "primary_version": "3.5.0.1392",
        "instance_id": r"PCI\VEN_14C3&DEV_7961&SUBSYS_E0B7105B&REV_00\4&1CDAF9ED&0&0011",
    }
    assert dc._reject_mediatek_mscatalog_spurious(row, ctx) == "mediatek_ms_version_mismatch"


def test_reject_mediatek_mscatalog_raw_row_without_source() -> None:
    """Batch MSCatalog reject runs before source=microsoft is stamped on rows."""
    row = {
        "title": "MediaTek, Inc. Net Driver Update (26.30.3.64)",
        "version": "26.30.3.64",
        "update_id": "5238915f-2ff7-4aa5-9ae1-b2780d6a89c6",
    }
    ctx = {
        "vendor_key": "mediatek",
        "pnp_class": "Net",
        "primary_version": "3.5.0.1392",
    }
    assert dc._reject_mscatalog_row_for_ctx(row, ctx, "MediaTek Wi-Fi") == "mediatek_ms_version_mismatch"


def test_reject_mediatek_mscatalog_microsoft_catalog_source() -> None:
    """MSCatalogLTS rows use source=microsoft_catalog before offer assembly."""
    row = {
        "source": "microsoft_catalog",
        "title": "MediaTek, Inc. Net Driver Update (26.20.5.23)",
        "version": "26.20.5.23",
        "update_id": "7df23186-6e1d-4356-87ca-89809f2625af",
    }
    ctx = {
        "vendor_key": "mediatek",
        "pnp_class": "Net",
        "primary_version": "3.5.0.1392",
    }
    assert dc._reject_mscatalog_row_for_ctx(row, ctx, "MediaTek Wi-Fi") == "mediatek_ms_version_mismatch"


def test_reject_mediatek_mscatalog_stale_uwd_without_hwid() -> None:
    row = {
        "source": "microsoft_catalog_html",
        "title": "MediaTek, Inc. Net Driver Update (3.0.1.1338)",
        "version": "3.0.1.1338",
        "update_id": "d18ca84f-c2d6-437e-b33e-693a2d0c052d",
    }
    ctx = {
        "vendor_key": "mediatek",
        "pnp_class": "Net",
        "primary_version": "3.5.0.1392",
    }
    assert dc._reject_mscatalog_row_for_ctx(row, ctx, "MediaTek Wi-Fi") == "mediatek_ms_stale_unverified"


def test_wifi_spurious_ms_rejected_and_status_none_when_oem_reference() -> None:
    ctx = {"vendor_key": "mediatek", "pnp_class": "Net", "primary_version": "3.5.0.1392"}
    raw = [
        {
            "source": "microsoft_catalog",
            "title": "MediaTek, Inc. Net Driver Update (26.20.5.23)",
            "version": "26.20.5.23",
        },
        {
            "source": "microsoft_catalog",
            "title": "MediaTek, Inc. Net Driver Update (3.0.1.1338)",
            "version": "3.0.1.1338",
        },
        {
            "source": "oem",
            "title": "MediaTek MT7921/MT7922 Wi-Fi UWD Driver",
            "version": "3.3.3.760",
        },
    ]
    kept = [
        o for o in raw
        if not dc._reject_mediatek_mscatalog_spurious(o, ctx)
    ]
    assert len(kept) == 1
    offers = dc.enrich_offers_with_comparison(
        kept,
        "3.5.0.1392",
        device_ctx=ctx,
    )
    assert dc.summarize_offer_status(offers, device_ctx=ctx) == "none"
    assert dc.possible_coverage_gap(
        "3.5.0.1392", offers, status="none", device_ctx=ctx
    )


def test_bluetooth_same_version_newer_date_is_same() -> None:
    ctx = {
        "vendor_key": "mediatek",
        "pnp_class": "Bluetooth",
        "device_label": "MediaTek Bluetooth Adapter",
    }
    vs, note = dc.compare_driver_to_installed(
        "1.930.3.287",
        "1.930.3.287",
        installed_date="/Date(1674086400000)/",
        candidate_date="2023-02-09",
        source="oem",
        device_ctx=ctx,
    )
    assert vs == "same"
    assert "no version change" in note.lower()


def test_reference_older_oem_kept_for_wifi_radio() -> None:
    ctx = {
        "pnp_class": "Net",
        "device_label": "MediaTek Wi-Fi 6 MT7921 Wireless LAN Card",
        "vendor_key": "mediatek",
    }
    row = {
        "source": "oem",
        "title": "MediaTek MT7921/MT7922 Wi-Fi UWD Driver",
        "version": "3.3.3.760",
    }
    out = dc._recompare_offer_row(row, "3.5.0.1392", device_ctx=ctx)
    assert out.get("reference_older_oem")
    assert out["vs_installed"] == "older"
    displayed = dc.filter_offers_for_display([out])
    assert len(displayed) == 1


def test_wifi_oem_not_on_bluetooth_after_filter() -> None:
    row = {
        "source": "oem",
        "title": "MediaTek MT7921 Wi-Fi UWD Driver",
        "version": "3.3.0.540",
    }
    ctx = {
        "pnp_class": "Bluetooth",
        "device_label": "MediaTek Bluetooth Adapter",
        "vendor_key": "mediatek",
    }
    assert dc._filter_offers_for_device_ctx([row], ctx) == []


def test_coverage_gap_none_reason_label_official() -> None:
    assert dc.none_reason_display_label("coverage_gap") == "No official match — recheck"


def test_reject_airplane_mode_on_dell_monitor() -> None:
    row = {
        "source": "oem",
        "title": "Dell Airplane Mode Switch Driver",
        "version": "1.4.11.0",
    }
    ctx = {
        "pnp_class": "monitor",
        "device_label": "Dell Alienware 17 R5 AMD LGD06E3 Display",
        "pnp_manufacturer": "Dell",
        "vendor_key": "dell",
        "system_manufacturer": "Alienware",
    }
    assert dc._reject_oem_airplane_mode_mismatch(row, ctx) == "oem_airplane_mode_wrong_device"
    assert dc._filter_offers_for_device_ctx([row], ctx) == []


def test_airplane_mode_still_allowed_on_switch_device() -> None:
    row = {
        "source": "oem",
        "title": "Dell Airplane Mode Switch Driver",
        "version": "1.4.11.0",
    }
    ctx = {
        "pnp_class": "hidclass",
        "device_label": "Airplane Mode Switch",
        "pnp_manufacturer": "Dell",
        "vendor_key": "dell",
    }
    assert dc._reject_oem_airplane_mode_mismatch(row, ctx) is None


def test_reject_realtek_hd_on_inbox_hd_audio_controller() -> None:
    row = {
        "source": "oem",
        "title": "Realtek High Definition Audio Driver",
        "version": "6.0.9738.1",
    }
    ctx = {
        "pnp_class": "system",
        "device_label": "High Definition Audio Controller",
        "pnp_manufacturer": "Microsoft",
        "vendor_key": "microsoft",
        "primary_version": "10.0.26100.8521",
        "system_manufacturer": "Alienware",
    }
    assert dc._reject_oem_realtek_hd_on_inbox_hd_controller(row, ctx) == (
        "oem_realtek_hd_on_inbox_hd_controller"
    )
    assert dc._filter_offers_for_device_ctx([row], ctx) == []


def test_realtek_audio_keeps_stale_dell_hd_package_visible() -> None:
    row = {
        "source": "oem",
        "title": "Realtek High Definition Audio Driver",
        "version": "6.0.9738.1",
    }
    ctx = {
        "pnp_class": "media",
        "device_label": "Realtek Audio",
        "pnp_manufacturer": "Realtek",
        "vendor_key": "realtek",
        "primary_version": "6.0.9929.1",
        "system_manufacturer": "Alienware",
    }
    offers = dc._filter_offers_for_device_ctx([row], ctx)
    fin = dc._finalize_catalog_offers(offers, "6.0.9929.1", device_ctx=ctx)
    assert len(fin) == 1
    assert fin[0]["vs_installed"] == "same"
    assert "newer than this Dell package" in (fin[0].get("compare_note") or "")


def test_realtek_mscatalog_wdm_codec_trusted_as_newer() -> None:
    row = {
        "source": "microsoft",
        "title": "Realtek Semiconductor Corp. MEDIA Driver Update (6.0.9998.1)",
        "version": "6.0.9998.1",
        "products": "HDAUDIO\\FUNC_01&VEN_10EC&DEV_0295&SUBSYS_10280B5B",
    }
    ctx = {
        "pnp_class": "media",
        "device_label": "Realtek Audio",
        "target_device_name": "Realtek Audio",
        "vendor_key": "realtek",
        "primary_version": "6.0.9929.1",
        "instance_id": "HDAUDIO\\FUNC_01&VEN_10EC&DEV_0295&SUBSYS_10280B5B&REV_1000\\5&35e90671&0&0001",
        "pci_tokens": ["VEN_10EC", "DEV_0295", "SUBSYS_10280B5B"],
    }
    assert dc._realtek_wdm_mscatalog_trusted(row, ctx) is True
    fin = dc._finalize_catalog_offers([row], "6.0.9929.1", device_ctx=ctx)
    assert fin[0]["vs_installed"] == "newer"
    assert dc.summarize_offer_status(fin) == "newer"


if __name__ == "__main__":
    test_firmware_class_excluded_from_driver_scan()
    test_reject_hp_firmware_on_dell_system()
    test_reject_kaspersky_on_audio_endpoint()
    test_reject_firmware_package_on_normal_driver_device()
    test_filter_hides_informational_microsoft_rows()
    test_inbox_vs_vendor_version_is_uncertain_without_hwid()
    test_inbox_vs_vendor_allowed_when_hwid_verified()
    test_has_actionable_versioned_offer_skips_support_link()
    test_microsoft_deferred_when_vendor_has_version()
    test_reject_amd_system_driver_on_monitor()
    test_reject_amd_system_driver_on_streaming_audio()
    test_allow_amd_system_driver_on_gpio_without_hwid()
    test_reject_amd_system_driver_on_audio_coprocessor()
    test_reject_nvidia_display_on_virtual_audio()
    test_reject_apo_on_battery()
    test_realtek_wdm_vs_apo_version_uncertain()
    test_build_device_driver_comparison_skips_firmware()
    test_summarize_oem_authority_over_microsoft()
    test_microsoft_newer_without_hwid_does_not_drive_status()
    test_microsoft_newer_with_hwid_drives_status()
    test_oem_support_link_does_not_drive_newer_status()
    test_score_oem_row_prefers_versioned_device_match()
    test_oem_gpu_not_offered_for_battery_or_keyboard()
    test_oem_gpu_not_offered_for_usb_hub_without_match()
    test_oem_offers_from_rows_skips_unrelated_versioned_packages()
    test_filter_offers_drops_oem_gpu_on_peripheral()
    test_oem_row_cache_is_per_system_not_per_device()
    test_batch_chipset_uses_registry_installed_version()
    test_needs_catalog_refresh_when_cache_missing()
    test_normalize_oem_nested_dell_driverset()
    test_normalize_oem_date_dell_release_string()
    test_fetch_oem_catalog_for_system_bulk_rows()
    test_fetch_oem_deep_uses_bulk_catalog()
    test_system_has_oem_driver_catalog()
    test_resolve_chipset_installed_version()
    test_chipset_catalog_entry_resolves_registry_version()
    test_parse_dell_dup_manifest_sample()
    test_get_dell_oem_rows_local_dup_fallback()
    test_machine_fingerprint_includes_service_tag()
    test_cache_rejects_wrong_machine_on_load()
    test_is_catalog_stale_when_only_one_blob()
    test_amd_vendor_cache_key_per_gpu()
    test_nvidia_vendor_cache_key_matches_fetch()
    test_fetch_live_oem_msi_via_baseboard()
    test_persist_session_uses_warmed_oem_cache()
    test_is_catalog_stale_rejects_wrong_machine()
    test_chipset_context_includes_pnp_anchor()
    test_score_update_match_no_duplicate_vendor_bonus()
    test_nvidia_ctx_eligible_without_vendor_key()
    test_fetch_nvidia_uses_primary_lookup()
    test_nvidia_processfind_html_parser()
    test_nvidia_lookup_records_fallback_chain()
    test_amd_scrape_uses_download_center()
    test_intel_scrape_dsa_fallback()
    test_intel_chipset_scrape_dsa_fallback()
    test_nvidia_branch_vs_internal_compare_by_date()
    test_nvidia_internal_installed_uses_branch_from_programs()
    test_nvidia_internal_installed_uses_windows_display_version()
    test_clear_installed_package_versions_cache()
    test_nvidia_branch_versions_compare_normally()
    test_nvidia_psid_pfid_gtx_1060_from_pci_dev()
    test_nvidia_ajax_rejects_rtx610_on_gtx1060()
    test_intel_hint_skips_graphics_on_sata_ahci()
    test_intel_fetch_empty_on_non_driver_intel_row()
    test_gpu_version_profile_amd()
    test_gpu_version_profile_nvidia()
    test_chipset_version_profile_amd_plumbing()
    test_chipset_platform_version_profile_amd()
    test_chipset_version_profile_not_on_synthetic_row()
    test_amd_psp_is_chipset_plumbing()
    test_amd_chipset_suite_version_heuristic()
    test_nvidia_ctx_ineligible_for_hd_audio()
    test_oem_rejects_amd_gpu_on_nvidia_display()
    test_oem_rejects_realtek_ethernet_on_universal_service()
    test_oem_accepts_dell_realtek_pcie_on_gaming_2_5gbe()
    test_oem_accepts_dell_realtek_pcie_after_1125_30_branch()
    test_realtek_audio_mscatalog_not_hwid_verified_without_dev_match()
    test_realtek_nic_same_oem_family_1125_1168()
    test_realtek_nic_cross_scheme_equivalent_oem_vs_public()
    test_realtek_wdm_mscatalog_keeps_hwid_verified_over_higher_wrong_dev()
    test_should_defer_microsoft_when_oem_older_than_installed()
    test_should_skip_oem_for_realtek_net_even_with_manufacturer_newer()
    test_oem_rejects_realtek_on_nvidia_hd_audio()
    test_oem_rejects_dolby_app_on_nvidia_hd_audio()
    test_oem_rejects_ethernet_on_usb_xhci()
    test_oem_keywords_nvidia_audio_not_gpu()
    test_oem_keywords_nvidia_usbc_not_gpu()
    test_shared_rejects_amd_bulk_on_oem_monitor()
    test_wu_prefilter_rejects_amd_system_on_monitor()
    test_oem_rejects_nvidia_audio_on_realtek_device()
    test_reject_oem_on_third_party_ifi_dac()
    test_reject_oem_generic_support_on_logitech_mouse()
    test_oem_realtek_still_allowed_on_builtin_realtek_audio()
    test_reject_oem_on_unknown_usb_dac_brand()
    test_standard_usb_hid_does_not_receive_pc_oem_versioned_packages()
    test_filter_offers_uses_shared_rejects_for_oem()
    test_reject_oem_radio_chip_mismatch_on_generic_bluetooth()
    test_mediatek_mt7921_oem_not_rejected_for_chip_label()
    test_mediatek_batch_mscatalog_includes_name_fallbacks()
    test_reject_wifi_oem_on_mediatek_bluetooth_adapter()
    test_reject_bluetooth_oem_on_mediatek_wifi_card()
    test_mediatek_wifi_skips_amd_adrenalin_compare_gate()
    test_reject_mediatek_mscatalog_adrenalin_shaped_rows()
    test_reject_mediatek_mscatalog_raw_row_without_source()
    test_reject_mediatek_mscatalog_microsoft_catalog_source()
    test_reject_mediatek_mscatalog_stale_uwd_without_hwid()
    test_wifi_spurious_ms_rejected_and_status_none_when_oem_reference()
    test_bluetooth_same_version_newer_date_is_same()
    test_reference_older_oem_kept_for_wifi_radio()
    test_wifi_oem_not_on_bluetooth_after_filter()
    test_coverage_gap_none_reason_label_official()
    test_reject_airplane_mode_on_dell_monitor()
    test_airplane_mode_still_allowed_on_switch_device()
    test_reject_realtek_hd_on_inbox_hd_audio_controller()
    test_realtek_audio_keeps_stale_dell_hd_package_visible()
    test_realtek_mscatalog_wdm_codec_trusted_as_newer()
    print("driver catalog quality tests OK")
