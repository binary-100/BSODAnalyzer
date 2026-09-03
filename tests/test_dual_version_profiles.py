"""Fixture-based tests for dual-version driver profiles."""

from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

import driver_catalog as dc

_FIXTURES = Path(__file__).resolve().parent / "fixtures"
_INTEL_FIXTURE = _FIXTURES / "catalog_scan_intel_chipset_snippet.json"
_REALTEK_FIXTURE = _FIXTURES / "catalog_scan_realtek_audio_snippet.json"
_LEGACY_HDA_FIXTURE = _FIXTURES / "catalog_scan_realtek_legacy_hda_snippet.json"
_NETWORK_FIXTURE = _FIXTURES / "catalog_scan_network_snippet.json"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_intel_chipset_suite_version_heuristic() -> None:
    assert dc._looks_like_intel_chipset_package_version("10.1.19900.8770")
    assert dc._looks_like_intel_chipset_package_version("11.2.0.0")
    assert not dc._looks_like_intel_chipset_package_version("30.100.2417.30")
    assert not dc._looks_like_intel_chipset_package_version("2406.5.5.0")


def test_intel_serial_io_chipset_profile_from_fixture() -> None:
    data = _load(_INTEL_FIXTURE)
    entry = data["devices"][0]
    dev = {
        "device_class": entry["device_class"].lower(),
        "vendor_key": "intel",
        "name": entry["device_name"],
        "version": entry["installed_version"],
        "_installed_at_scan": entry["installed_version"],
    }
    suite = entry["expected_suite_version"]
    with mock.patch.object(
        dc, "_load_intel_chipset_suite_installed_version", return_value=suite
    ):
        profile = dc.build_chipset_version_profile(dev)
    assert profile is not None
    assert profile["vendor"] == "intel"
    assert profile["windows_installed"] == "30.100.2417.30"
    assert profile["mfr_installed"] == suite
    cell, tip = dc.format_chipset_installed_table_cell(profile)
    assert "30.100.2417.30" in cell
    assert f"Chipset {suite}" in cell
    assert "Intel Chipset INF" in tip


def test_intel_me_is_chipset_plumbing_but_separate_profile() -> None:
    data = _load(_INTEL_FIXTURE)
    entry = data["devices"][1]
    ctx = {"device_label": entry["device_name"].lower(), "vendor_key": "intel"}
    assert dc._device_is_intel_chipset_plumbing(ctx)
    assert dc._device_is_intel_me_device(ctx)
    dev = {
        "device_class": entry["device_class"].lower(),
        "vendor_key": "intel",
        "name": entry["device_name"],
        "version": entry["installed_version"],
        "_installed_at_scan": entry["installed_version"],
    }
    me_pkg = "2414.5.4.0"
    with mock.patch.object(
        dc, "_load_intel_me_installed_version", return_value=me_pkg
    ), mock.patch.object(
        dc, "_load_intel_chipset_suite_installed_version", return_value="10.1.19900.8770"
    ):
        assert dc.build_chipset_version_profile(dev) is None
        profile = dc.build_intel_me_version_profile(dev)
    assert profile is not None
    assert profile["windows_installed"] == "2406.5.5.0"
    assert profile["mfr_installed"] == me_pkg
    cell, tip = dc.format_intel_me_installed_table_cell(profile)
    assert "2406.5.5.0" in cell
    assert me_pkg in cell
    assert "Intel ME Components" in tip


def test_oem_rejects_intel_chipset_on_serial_io() -> None:
    data = _load(_INTEL_FIXTURE)
    entry = data["devices"][1]
    row = {"source": "oem", "title": "Intel Chipset Driver", "version": "10.1.19900.8770"}
    ctx = {
        "device_label": entry["device_name"].lower(),
        "vendor_key": "intel",
        "primary_version": entry["installed_version"],
    }
    assert dc._reject_oem_amd_chipset_on_component_inf(row, ctx) is None
    assert dc._reject_oem_intel_chipset_on_component_inf(row, ctx)


def test_realtek_wdm_profile_from_fixture() -> None:
    data = _load(_REALTEK_FIXTURE)
    inv = data["inventory"]
    entry = data["devices"][0]
    dev = {
        "device_class": entry["device_class"].lower(),
        "vendor_key": "realtek",
        "name": entry["device_name"],
        "display_name": entry["display_name"],
        "version": entry["installed_version"],
        "_installed_at_scan": entry["installed_version"],
    }
    profile = dc.build_realtek_audio_version_profile(dev, inventory=inv)
    assert profile is not None
    assert profile["role"] == "wdm"
    assert profile["windows_installed"] == "6.0.9929.1"
    assert profile["mfr_installed"] == entry["companion_version"]
    cell, tip = dc.format_realtek_audio_installed_table_cell(profile)
    assert "6.0.9929.1" in cell
    assert "Effects 13.0.6000.1905" in cell
    assert "WDM codec" in tip


def test_realtek_effects_row_profile_from_fixture() -> None:
    data = _load(_LEGACY_HDA_FIXTURE)
    entry = data["devices"][1]
    inv = [
        {
            "name": "Realtek Audio",
            "display_name": "Realtek Audio",
            "device_class": "MEDIA",
            "version": entry["companion_version"],
        }
    ]
    dev = {
        "device_class": entry["device_class"].lower(),
        "vendor_key": "realtek",
        "name": entry["device_name"],
        "display_name": entry["display_name"],
        "version": entry["installed_version"],
        "_installed_at_scan": entry["installed_version"],
    }
    profile = dc.build_realtek_audio_version_profile(dev, inventory=inv)
    assert profile is not None
    assert profile["role"] == "apo"
    assert profile["windows_installed"] == "13.0.6000.1905"
    assert profile["mfr_installed"] == entry["companion_version"]


def test_realtek_legacy_hda_profile_from_fixture() -> None:
    data = _load(_LEGACY_HDA_FIXTURE)
    inv = data["inventory"]
    entry = data["devices"][0]
    dev = {
        "device_class": entry["device_class"].lower(),
        "vendor_key": "realtek",
        "name": entry["device_name"],
        "display_name": entry["display_name"],
        "version": entry["installed_version"],
        "_installed_at_scan": entry["installed_version"],
    }
    profile = dc.build_realtek_audio_version_profile(dev, inventory=inv)
    assert profile is not None
    assert profile["role"] == "hda_legacy"
    assert profile["windows_installed"] == "R2.82"
    assert profile["mfr_installed"] == entry["companion_version"]


def test_realtek_nic_profile_from_fixture() -> None:
    data = _load(_NETWORK_FIXTURE)
    entry = data["devices"][0]
    dev = {
        "device_class": entry["device_class"].lower(),
        "pnp_class": entry["device_class"].lower(),
        "vendor_key": entry["vendor_key"],
        "name": entry["device_name"],
        "display_name": entry["display_name"],
        "version": entry["installed_version"],
        "_installed_at_scan": entry["installed_version"],
    }
    pkg = entry["expected_package_version"]
    with mock.patch.object(
        dc, "_load_realtek_ethernet_installed_version", return_value=pkg
    ):
        profile = dc.build_network_version_profile(dev)
    assert profile is not None
    assert profile["kind"] == "realtek_nic"
    assert profile["windows_installed"] == entry["installed_version"]
    assert profile["mfr_installed"] == pkg


def test_intel_wireless_profile_from_fixture() -> None:
    data = _load(_NETWORK_FIXTURE)
    entry = data["devices"][1]
    dev = {
        "device_class": entry["device_class"].lower(),
        "pnp_class": entry["device_class"].lower(),
        "vendor_key": entry["vendor_key"],
        "name": entry["device_name"],
        "display_name": entry["display_name"],
        "version": entry["installed_version"],
        "_installed_at_scan": entry["installed_version"],
    }
    suite = entry["expected_suite_version"]
    with mock.patch.object(
        dc, "_load_intel_wireless_installed_version", return_value=suite
    ):
        profile = dc.build_network_version_profile(dev)
    assert profile is not None
    assert profile["kind"] == "intel_wireless"
    assert profile["mfr_installed"] == suite


def test_killer_network_profile_from_fixture() -> None:
    data = _load(_NETWORK_FIXTURE)
    entry = data["devices"][2]
    dev = {
        "device_class": entry["device_class"].lower(),
        "pnp_class": entry["device_class"].lower(),
        "vendor_key": entry["vendor_key"],
        "name": entry["device_name"],
        "display_name": entry["display_name"],
        "version": entry["installed_version"],
        "_installed_at_scan": entry["installed_version"],
    }
    suite = entry["expected_suite_version"]
    with mock.patch.object(
        dc, "_load_killer_suite_installed_version", return_value=suite
    ):
        profile = dc.build_network_version_profile(dev)
    assert profile is not None
    assert profile["kind"] == "killer"
    assert profile["mfr_installed"] == suite


def test_register_installed_package_from_name() -> None:
    out: dict[str, str] = {}
    dc._register_installed_package_from_name(
        out, "Intel(R) Chipset Device Software", "10.1.19900.8770"
    )
    dc._register_installed_package_from_name(
        out, "Intel(R) Management Engine Components", "2414.5.4.0"
    )
    dc._register_installed_package_from_name(
        out, "Intel(R) PROSet/Wireless WiFi Software", "23.140.0.1"
    )
    dc._register_installed_package_from_name(
        out, "Killer Performance Suite", "3.1122.1122.1"
    )
    dc._register_installed_package_from_name(
        out, "Realtek Ethernet Controller Driver", "10.071.0315.2023"
    )
    assert out["intel_chipset"] == "10.1.19900.8770"
    assert out["intel_me"] == "2414.5.4.0"
    assert out["intel_wireless"] == "23.140.0.1"
    assert out["killer_suite"] == "3.1122.1122.1"
    assert out["realtek_ethernet"] == "10.071.0315.2023"


def test_attach_all_dual_version_profiles_priority() -> None:
    dev = {
        "device_class": "display",
        "vendor_key": "nvidia",
        "name": "NVIDIA GeForce RTX 4080",
        "version": "32.0.15.6094",
        "_installed_at_scan": "32.0.15.6094",
    }
    with mock.patch.object(
        dc, "_load_nvidia_branch_installed_version", return_value="566.03"
    ):
        dc.attach_all_dual_version_profiles(dev)
    key, _ = dc.pick_dual_version_profile(dev)
    assert key == "_gpu_version_profile"


def test_export_universe_prefers_full_driver_rows() -> None:
    import driver_list_build as drvlist

    prof = {
        "bios_driver_info": {
            "device_inventory": [
                {"name": "Intel Wi-Fi", "version": "1.0", "driver": "netwtw08.sys"},
            ],
            "all_drivers": [
                {"name": f"Device {i}", "version": "1.0", "driver": "x.sys"}
                for i in range(120)
            ],
        },
        "system_ctx": {},
    }
    lite = drvlist.driver_rows_for_cache(prof, full=False)
    full = drvlist.driver_rows_for_cache(prof, full=True)
    assert len(lite) == 1
    assert len(full) == 120


if __name__ == "__main__":
    test_intel_chipset_suite_version_heuristic()
    test_intel_serial_io_chipset_profile_from_fixture()
    test_intel_me_is_chipset_plumbing_but_separate_profile()
    test_oem_rejects_intel_chipset_on_serial_io()
    test_realtek_wdm_profile_from_fixture()
    test_realtek_effects_row_profile_from_fixture()
    test_realtek_legacy_hda_profile_from_fixture()
    test_realtek_nic_profile_from_fixture()
    test_intel_wireless_profile_from_fixture()
    test_killer_network_profile_from_fixture()
    test_register_installed_package_from_name()
    test_attach_all_dual_version_profiles_priority()
    test_export_universe_prefers_full_driver_rows()
    print("dual_version_profiles tests OK")
