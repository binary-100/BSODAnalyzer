"""OEM effective version + dual-baseline gate (Phases A/B)."""

from __future__ import annotations

import os
import tempfile
from unittest import mock

import driver_catalog as dc
import oem_effective_version as oev
import oem_enterprise_catalog as oec


def test_pick_inner_version_realtek_8125() -> None:
    inner = [
        {
            "version": "1125.028.1224.2025",
            "pci": [{"vendor_id": "10EC", "device_id": "8125"}],
        },
        {
            "version": "1168.028.1224.2025",
            "pci": [{"vendor_id": "10EC", "device_id": "8168"}],
        },
    ]
    ctx = {
        "instance_id": r"PCI\VEN_10EC&DEV_8125&SUBSYS_10281462&REV_05",
        "pci_tokens": ["VEN_10EC", "DEV_8125", "SUBSYS_10281462"],
        "vendor_key": "realtek",
        "pnp_class": "net",
    }
    ver, _ = oev.pick_inner_version_for_ctx(inner, ctx)
    assert ver == "1125.028.1224.2025"


def test_resolve_offer_effective_version_from_offer() -> None:
    offer = {
        "source": "oem",
        "source_label": "OEM (Dell / Alienware)",
        "version": "1168.28.1224.2025",
        "inner_versions": [
            {
                "version": "1125.028.1224.2025",
                "pci": [{"vendor_id": "10EC", "device_id": "8125"}],
            },
        ],
    }
    ctx = {"pci_tokens": ["VEN_10EC", "DEV_8125"], "vendor_key": "realtek", "pnp_class": "net"}
    eff, method, _ = oev.resolve_offer_effective_version(offer, ctx)
    assert eff == "1125.028.1224.2025"
    assert method == "oem_inner_pci_version"


def test_extract_oem_inner_versions_from_json() -> None:
    payload = {
        "title": "Intel Wi-Fi Driver",
        "version": "23.120.0",
        "supportedDevices": [
            {
                "version": "23.120.0.2",
                "pciInfo": [{"vendorID": "8086", "deviceID": "51F0"}],
            },
        ],
    }
    inner = oev.extract_oem_inner_versions_from_item(payload)
    assert inner
    assert inner[0]["version"] == "23.120.0.2"
    assert inner[0]["pci"][0]["vendor_id"] == "8086"


def test_dual_baseline_gate_blocks_alt_baseline_newer() -> None:
    ctx = {
        "vendor_key": "realtek",
        "pnp_class": "net",
        "device_label": "Realtek PCIe 2.5GbE",
        "primary_version": "1125.30.50.508",
        "pci_tokens": ["VEN_10EC", "DEV_8125"],
    }
    offer = {
        "source": "oem",
        "source_label": "OEM (Dell / Alienware)",
        "version": "1168.28.1224.2025",
        "inner_versions": [
            {
                "version": "1125.028.1224.2025",
                "pci": [{"vendor_id": "10EC", "device_id": "8125"}],
            },
        ],
        "vs_installed": "newer",
        "verification_method": "alternate_installed_baseline",
    }
    with mock.patch.object(
        dc,
        "_alternate_installed_baselines",
        return_value=["1168.008.0515.2022"],
    ):
        gated = dc._apply_dual_baseline_gate(
            offer,
            "1125.30.50.508",
            "",
            ctx,
        )
    assert gated["vs_installed"] in ("same", "uncertain")
    assert gated.get("verification_method") == "dual_baseline_gate"


def test_recompare_uses_inner_not_wrapper() -> None:
    ctx = {
        "vendor_key": "realtek",
        "pnp_class": "net",
        "pci_tokens": ["VEN_10EC", "DEV_8125"],
    }
    row = {
        "source": "oem",
        "title": "Realtek PCIe Ethernet Controller Driver",
        "version": "1168.28.1224.2025",
        "inner_versions": [
            {
                "version": "1125.028.1224.2025",
                "pci": [{"vendor_id": "10EC", "device_id": "8125"}],
            },
        ],
        "install_verified": True,
        "url": "https://downloads.dell.com/example.exe",
    }
    out = dc._recompare_offer_row(row, "1125.30.50.508", "", device_ctx=ctx)
    assert out.get("offer_effective_version") == "1125.028.1224.2025"
    assert out.get("vs_installed") in ("same", "older", "uncertain")


def test_parse_dell_dup_manifest_inner_versions() -> None:
    sample = """<?xml version="1.0" encoding="utf-16"?>
<Manifest baseLocation="downloads.dell.com" xmlns="openmanage/cm/dm">
  <SoftwareComponent vendorVersion="1168.28.1224.2025" releaseID="GD26K" releaseDate="May 11, 2026"
    path="FOLDER/Realtek-PCIe-Ethernet-Controller-Driver_GD26K.EXE">
    <Name><Display lang="en"><![CDATA[Realtek PCIe Ethernet Controller Driver]]></Display></Name>
    <Category value="NI"><Display lang="en"><![CDATA[Network]]></Display></Category>
    <SupportedDCHDevices>
      <Device componentID="103014" version="1125.028.1224.2025">
        <PCIInfo deviceID="8125" vendorID="10EC" subDeviceID="" subVendorID="" />
      </Device>
    </SupportedDCHDevices>
  </SoftwareComponent>
</Manifest>"""
    with tempfile.NamedTemporaryFile("w", encoding="utf-16", suffix=".xml", delete=False) as fh:
        fh.write(sample)
        path = fh.name
    try:
        rows = dc._parse_dell_dup_manifest(path)
    finally:
        os.unlink(path)
    eth = next(r for r in rows if "Realtek PCIe Ethernet" in r["title"])
    assert eth["version"] == "1168.28.1224.2025"
    assert eth.get("inner_versions")
    assert eth["inner_versions"][0]["version"] == "1125.028.1224.2025"


def test_merge_dell_dup_inner_into_api_rows() -> None:
    api_rows = [{
        "title": "Realtek PCIe Ethernet Controller Driver",
        "version": "1168.28.1224.2025",
        "url": "https://downloads.dell.com/example.exe",
    }]
    dup_rows = [{
        "title": "Realtek PCIe Ethernet Controller Driver",
        "version": "1168.28.1224.2025",
        "inner_versions": [{
            "version": "1125.028.1224.2025",
            "pci": [{"vendor_id": "10EC", "device_id": "8125"}],
        }],
    }]
    with mock.patch.object(
        dc, "_get_dell_oem_rows_from_local_dup", return_value=dup_rows
    ):
        merged = dc._merge_dell_dup_inner_versions_into_rows(api_rows, {})
    assert merged[0].get("inner_versions")
    assert merged[0]["inner_versions"][0]["version"] == "1125.028.1224.2025"


def test_merge_dup_inner_enriches_enterprise_release_rows() -> None:
    enterprise_rows = [{
        "title": "Realtek PCIe Ethernet Controller Driver",
        "version": "1168.28.1224.2025",
        "url": "https://www.dell.com/support/driverId/GD26K",
    }]
    dup_rows = [{
        "title": "Realtek PCIe Ethernet Controller Driver",
        "version": "1168.28.1224.2025",
        "inner_versions": [{
            "version": "1125.028.1224.2025",
            "pci": [{"vendor_id": "10EC", "device_id": "8125"}],
        }],
    }]
    merged = dc._merge_dup_inner_versions_into_rows(enterprise_rows, dup_rows)
    assert merged[0]["inner_versions"][0]["version"] == "1125.028.1224.2025"


def test_fetch_dell_oem_rows_live_enriches_inner_after_enterprise() -> None:
    api_rows = [{"title": "Dell API Driver", "version": "1.0", "url": "https://dell/api"}]
    ent_rows = [{
        "title": "Realtek PCIe Ethernet Controller Driver",
        "version": "1168.28.1224.2025",
        "url": "https://dell/ent",
    }]
    dup_rows = [{
        "title": "Realtek PCIe Ethernet Controller Driver",
        "version": "1168.28.1224.2025",
        "inner_versions": [{"version": "1125.028.1224.2025", "pci": []}],
    }]
    with mock.patch.object(dc, "_get_dell_oem_rows_from_api", return_value=list(api_rows)), mock.patch.object(
        dc, "_get_dell_oem_rows_from_local_dup", return_value=list(dup_rows)
    ), mock.patch.object(oec, "dell_enterprise_rows", return_value=list(ent_rows)):
        oec.clear_session_cache()
        rows, _ = dc._fetch_dell_oem_rows_live({"system_manufacturer": "Dell Inc."})
    eth = next(r for r in rows if "Realtek PCIe Ethernet" in r["title"])
    assert eth.get("inner_versions")


if __name__ == "__main__":
    test_pick_inner_version_realtek_8125()
    test_resolve_offer_effective_version_from_offer()
    test_extract_oem_inner_versions_from_json()
    test_dual_baseline_gate_blocks_alt_baseline_newer()
    test_recompare_uses_inner_not_wrapper()
    test_parse_dell_dup_manifest_inner_versions()
    test_merge_dell_dup_inner_into_api_rows()
    print("All test_oem_effective_version tests passed.")
