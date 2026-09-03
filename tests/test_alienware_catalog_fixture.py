"""Regression tests from Alienware m17 R5 catalog scan export (2026-06-22)."""

from __future__ import annotations

import json
from pathlib import Path

import driver_catalog as dc

_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "catalog_scan_alienware_m17_r5_snippet.json"


def _load_fixture() -> dict:
    return json.loads(_FIXTURE.read_text(encoding="utf-8"))


def _ctx_for_device(entry: dict) -> dict:
    name = entry["device_name"]
    display = entry.get("display_name") or name
    return {
        "pnp_class": (entry.get("device_class") or "").lower(),
        "device_label": display,
        "target_device_name": name,
        "display_name": display,
        "vendor_key": "realtek" if "realtek" in name.lower() else "amd",
        "primary_version": entry.get("installed_version") or "",
        "installed_rows": [{"name": name, "version": entry.get("installed_version") or ""}],
    }


def test_fixture_amd_audio_rejects_realtek_oem() -> None:
    data = _load_fixture()
    for entry in data["devices"]:
        for title in entry.get("expected_oem_rejects") or []:
            row = {"source": "oem", "title": title, "version": "6.0.9738.1"}
            ctx = _ctx_for_device(entry)
            if "AMD Chipset" in title:
                assert dc._reject_oem_amd_chipset_on_component_inf(row, ctx)
            else:
                assert dc._shared_catalog_row_rejects(row, ctx)
                assert dc._filter_offers_for_device_ctx([row], ctx, min_oem_score=2) == []


def test_fixture_realtek_nic_oem_accepted_and_status_newer() -> None:
    data = _load_fixture()
    entry = next(
        d for d in data["devices"]
        if d["device_name"] == "Realtek Gaming 2.5GbE Family Controller"
    )
    ctx = _ctx_for_device(entry)
    for spec in entry.get("expected_oem_accepts") or []:
        row = {"source": "oem", "title": spec["title"], "version": spec["version"]}
        assert dc._shared_catalog_row_rejects(row, ctx) is None
        assert dc._oem_row_eligible_for_ctx(row, ctx)
    offers = dc.enrich_offers_with_comparison(
        [
            {
                "source": "oem",
                "source_label": "OEM (Dell / Alienware)",
                "title": "Realtek PCIe Ethernet Controller Driver",
                "version": "1168.28.1224.2025",
            },
            {
                "source": "vendor",
                "source_label": "Manufacturer (Realtek)",
                "title": "Install_PCIE_Win11.zip",
                "version": "11.029.50",
                "date": "2026-04-24",
            },
        ],
        entry["installed_version"],
        device_ctx=ctx,
    )
    assert dc.summarize_offer_status(offers) == entry.get(
        "expected_status_after_fix", "newer"
    )


def test_fixture_realtek_audio_coverage_gap_without_valid_offers() -> None:
    data = _load_fixture()
    entry = next(d for d in data["devices"] if d["device_name"] == "Realtek Audio")
    assert dc.possible_coverage_gap(
        entry["installed_version"], [], status="none"
    )


def test_expand_primary_catalog_includes_nic_and_gpu() -> None:
    import driver_list_build as dl

    cache = [
        {
            "name": "Realtek Gaming 2.5GbE Family Controller",
            "device_class": "NET",
            "version": "1125.28.1224.2025",
        },
        {
            "name": "NVIDIA GeForce RTX 3070 Ti Laptop GPU",
            "device_class": "DISPLAY",
            "version": "32.0.16.1047",
        },
        {"name": "Other Device", "device_class": "SYSTEM", "version": "1.0"},
    ]
    names = dl.expand_primary_catalog_device_names(["Other Device"], cache)
    assert "Realtek Gaming 2.5GbE Family Controller" in names
    assert "NVIDIA GeForce RTX 3070 Ti Laptop GPU" in names


if __name__ == "__main__":
    test_fixture_amd_audio_rejects_realtek_oem()
    test_fixture_realtek_nic_oem_accepted_and_status_newer()
    test_fixture_realtek_audio_coverage_gap_without_valid_offers()
    test_expand_primary_catalog_includes_nic_and_gpu()
    print("Alienware catalog fixture tests OK")
