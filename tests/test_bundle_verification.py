"""Tests for unified bundle verification (component compare + status rollup)."""

from __future__ import annotations

import json
from unittest import mock

import bundle_verification as bv
from amd_chipset_manifest import amd_info_products_to_bundle_components, parse_info_products
import catalog_amd_chipset_manifest as acm
import catalog_amd_fetch as amd_fetch
import catalog_intel_fetch as intel_fetch
import intel_chipset_manifest as icm


def test_compare_bundle_detects_stale_smbus_while_wrapper_same() -> None:
    installed = [
        {"label": "PSP", "device_name": "AMD PSP 11.0 Device", "version": "5.46.0.0"},
        {"label": "SMBus", "device_name": "AMD SMBUS", "version": "2.0.0.26"},
        {"label": "GPIO", "device_name": "AMD GPIO Controller", "version": "2.2.0.137"},
    ]
    offer = [
        {"label": "PSP", "device_name": "AMD PSP Driver", "version": "5.46.0.0"},
        {"label": "SMBus", "device_name": "AMD SMBUS Driver", "version": "5.12.0.44"},
        {"label": "GPIO", "device_name": "AMD GPIO Driver", "version": "2.2.0.137"},
    ]
    details, rollup, note = bv.compare_bundle_component_sets(installed, offer)
    assert rollup == "newer"
    assert any(d["label"] == "SMBus" and d["vs_offer"] == "newer" for d in details)
    assert "SMBus" in note


def test_apply_bundle_status_rollup_upgrades_same_to_newer() -> None:
    installed = [{"label": "SMBus", "version": "2.0.0.26", "device_name": "AMD SMBUS"}]
    offers = [
        {
            "source": "vendor",
            "version": "8.08.12.551",
            "vs_installed": "same",
            "bundle_components": [
                {"label": "SMBus", "version": "5.12.0.44", "device_name": "AMD SMBUS Driver"},
            ],
        }
    ]
    status, details, note = bv.apply_bundle_status_rollup(
        "same",
        installed_components=installed,
        offers=offers,
        wrapper_status="same",
    )
    assert status == "newer"
    assert details
    assert note


def test_amd_info_xml_to_bundle_components() -> None:
    xml = """
    <Products>
      <Product>
        <OS>Windows 11</OS>
        <Name>AMD SMBUS Driver</Name>
        <Version>5.12.0.44</Version>
      </Product>
      <Product>
        <OS>Windows 10</OS>
        <Name>AMD SMBUS Driver</Name>
        <Version>5.11.0.0</Version>
      </Product>
    </Products>
    """
    products = parse_info_products(xml, os_filter="Windows 11")
    components = amd_info_products_to_bundle_components(products)
    assert len(components) == 1
    assert components[0]["label"] == "SMBus"
    assert components[0]["version"] == "5.12.0.44"


def test_inner_versions_to_bundle_components() -> None:
    inner = [
        {"version": "616.64", "name": "NVIDIA Graphics Driver"},
        {"version": "1.2.3.4", "name": "NVIDIA Thermal Controller"},
    ]
    rows = bv.bundle_components_from_inner_versions(inner)
    assert len(rows) == 2
    assert rows[1]["label"] == "Thermal"


def test_extract_amd_chipset_download_url_prefers_exe() -> None:
    html = """
    <a href="https://www.amd.com/en/support/chipset-software">Chipset</a>
    <script>{"downloadUrl":"https://drivers.amd.com/drivers/chipset/AMD_Chipset_Software.exe"}</script>
    """
    url = acm.extract_amd_chipset_download_url(html, "https://www.amd.com/en/support/chipset")
    assert url.endswith(".exe")
    assert "chipset" in url.lower()


def test_manifest_cache_roundtrip(tmp_path) -> None:
    components = [{"label": "SMBus", "version": "5.12.0.44", "device_name": "AMD SMBUS Driver"}]
    with mock.patch.object(acm, "manifest_cache_file", return_value=tmp_path / "manifest.json"):
        acm.save_cached_bundle_components("8.08.12.551", components, source_url="https://example/pkg.exe")
        loaded = acm.load_cached_bundle_components("8.08.12.551")
    assert loaded == components


def test_fetch_amd_chipset_bundle_components_uses_cache(tmp_path) -> None:
    components = [{"label": "SMBus", "version": "5.12.0.44", "device_name": "AMD SMBUS Driver"}]
    cache_file = tmp_path / "manifest_8.08.12.551.json"
    cache_file.write_text(
        json.dumps({"suite_version": "8.08.12.551", "bundle_components": components}),
        encoding="utf-8",
    )
    with mock.patch.object(acm, "manifest_cache_file", return_value=cache_file):
        rows = acm.fetch_amd_chipset_bundle_components("8.08.12.551", {"hw_category": "chipset"})
    assert rows == components


def test_fetch_amd_driver_offers_attaches_bundle_components() -> None:
    import driver_catalog as dc

    ctx = {
        "vendor_key": "amd",
        "hw_category": "chipset",
        "pnp_class": "system",
        "device_label": "AMD Chipset",
    }
    components = [{"label": "SMBus", "version": "5.12.0.44", "device_name": "AMD SMBUS Driver"}]
    with (
        mock.patch.object(dc, "_manufacturer_vendor_lookup_applicable", return_value=True),
        mock.patch.object(dc, "_amd_vendor_version_lookup_applicable", return_value=True),
        mock.patch.object(dc, "_vendor_scrape_cache_get", return_value=("8.08.12.551", "")),
        mock.patch.object(dc, "_looks_like_amd_chipset_package_version", return_value=True),
        mock.patch.object(acm, "fetch_amd_chipset_bundle_components", return_value=components),
    ):
        offers = amd_fetch.fetch_amd_driver_offers(ctx)
    assert len(offers) == 1
    assert offers[0]["bundle_components"] == components


def test_graphics_bundle_rollup_upgrades_stale_npcf() -> None:
    from catalog_device_profiles import collect_graphics_bundle_installed_components

    inventory = [
        {
            "catalog_role": "gpu_companion",
            "name": "NVIDIA Platform Controllers and Framework",
            "version": "1.0.0.1",
        }
    ]
    installed = collect_graphics_bundle_installed_components(
        inventory,
        primary_version="32.0.16.1088",
        video_controllers=[{"name": "NVIDIA GeForce RTX 3080", "driver_version": "32.0.16.1088"}],
    )
    offers = [
        {
            "source": "oem",
            "title": "NVIDIA GeForce RTX Graphics Driver",
            "version": "32.0.16.1088",
            "inner_versions": [
                {"name": "NVIDIA Graphics Driver", "version": "32.0.16.1088"},
                {"name": "NVIDIA Platform Controllers and Framework", "version": "32.0.16.1100"},
            ],
        }
    ]
    result: dict = {}
    bv.attach_wrapper_row_bundle_rollup(
        result,
        installed_components=installed,
        offers=offers,
        wrapper_status="same",
    )
    assert result.get("bundle_status_rollup") == "newer"
    assert any(d.get("label") == "NPCF" for d in result.get("bundle_component_compare") or [])


def test_intel_infs_to_bundle_components_skips_suite_wrapper() -> None:
    entries = [
        (
            "Chipset.inf",
            '[Version]\nDriverVer=06/21/2024,10.1.20398.8776\nProvider="Intel Corporation"\n',
        ),
        (
            "SerialIO.inf",
            '[Version]\nDriverVer=06/21/2024,10.1.1.45\nProvider="Intel Corporation"\n',
        ),
        (
            "SmbUS.inf",
            '[Version]\nDriverVer=06/21/2024,10.1.1.46\nProvider="Intel Corporation"\n',
        ),
    ]
    components = icm.intel_infs_to_bundle_components(entries)
    labels = {c["label"] for c in components}
    assert "Serial IO" in labels
    assert "SMBus" in labels
    assert "Chipset INF" not in labels
    smbus = next(c for c in components if c["label"] == "SMBus")
    assert smbus["version"] == "10.1.1.46"


def test_intel_infs_from_zip_fixture(tmp_path) -> None:
    import zipfile

    zpath = tmp_path / "chipset.zip"
    with zipfile.ZipFile(zpath, "w") as zf:
        zf.writestr(
            "Drivers/SerialIO.inf",
            '[Version]\nDriverVer=06/21/2024,10.1.1.45\n',
        )
        zf.writestr(
            "Drivers/SmbUS.inf",
            '[Version]\nDriverVer=06/21/2024,10.1.1.46\n',
        )
    entries = icm.read_infs_from_zip(zpath)
    components = icm.intel_infs_to_bundle_components(entries)
    assert len(components) == 2


def test_fetch_intel_driver_offers_attaches_bundle_components() -> None:
    import driver_catalog as dc

    ctx = {
        "vendor_key": "intel",
        "hw_category": "chipset",
        "pnp_class": "system",
        "device_label": "Intel Chipset",
    }
    components = [
        {"label": "Serial IO", "version": "10.1.1.45", "device_name": "SerialIO.inf"},
        {"label": "SMBus", "version": "10.1.1.46", "device_name": "SmbUS.inf"},
    ]
    with (
        mock.patch.object(dc, "_manufacturer_vendor_lookup_applicable", return_value=True),
        mock.patch.object(dc, "_intel_driver_hint_from_ctx", return_value="chipset"),
        mock.patch.object(dc, "_vendor_scrape_cache_get", return_value=("10.1.20398.8776", "", "https://intel.test", "")),
        mock.patch.object(dc, "_v6_catalog_enabled", return_value=False),
        mock.patch(
            "catalog_intel_chipset_manifest.fetch_intel_chipset_bundle_components",
            return_value=components,
        ),
    ):
        offers = intel_fetch.fetch_intel_driver_offers(ctx)
    vendor = next(o for o in offers if o.get("source") == "vendor")
    assert vendor["bundle_components"] == components


def test_bundle_compare_rows_from_catalog_entry_synthesizes() -> None:
    entry = {
        "chipset_bundle_components": [
            {"label": "SMBus", "version": "2.0.0.26"},
            {"label": "PSP", "version": "5.46.0.0"},
        ],
        "bundle_offer_components": [
            {"label": "SMBus", "version": "5.12.0.44"},
            {"label": "PSP", "version": "5.46.0.0"},
        ],
    }
    rows = bv.bundle_compare_rows_from_catalog_entry(entry)
    assert len(rows) == 2
    smbus = next(r for r in rows if r.get("label") == "SMBus")
    assert smbus.get("vs_offer") == "newer"


def test_format_bundle_compare_export_lines() -> None:
    entry = {
        "bundle_component_compare": [
            {
                "label": "SMBus",
                "installed_version": "2.0.0.26",
                "offer_version": "5.12.0.44",
                "vs_offer": "newer",
            },
        ],
        "bundle_compare_note": "Bundle wrapper matches but SMBus is stale.",
    }
    lines = bv.format_bundle_compare_export_lines(entry)
    assert any("SMBus" in ln for ln in lines)
    assert any("Stale" in ln for ln in lines)
    assert any("Bundle note" in ln for ln in lines)
