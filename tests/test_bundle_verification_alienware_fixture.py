"""Alienware m17 R5 AMD bundle verification fixture — suite same, SMBus stale."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import bundle_verification as bv
from catalog_offer_status import summarize_offer_status

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(_ROOT / "scripts"))

_FIXTURE = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "bundle_verification_alienware_m17_r5_amd.json"
)


def _load_fixture() -> dict:
    return json.loads(_FIXTURE.read_text(encoding="utf-8"))


def test_alienware_fixture_smbus_stale_rollup() -> None:
    data = _load_fixture()
    plat = data["chipset_platform"]
    installed = plat["installed_components"]
    offer_components = plat["offer_bundle_components"]
    offers = [
        {
            "source": "vendor",
            "source_label": "Manufacturer (AMD)",
            "title": "AMD Chipset Software",
            "version": plat["wrapper_offer_version"],
            "bundle_components": offer_components,
            "vs_installed": plat["wrapper_status"],
        }
    ]
    result: dict = {
        "installed_version": plat["suite_installed"],
        "chipset_bundle_components": installed,
        "offers": offers,
    }
    wrapper = summarize_offer_status(offers)
    assert wrapper == plat["wrapper_status"]
    bv.attach_wrapper_row_bundle_rollup(
        result,
        installed_components=installed,
        offers=offers,
        wrapper_status=wrapper,
    )
    assert result.get("bundle_status_rollup") == plat["expected_rollup_status"]
    stale = bv.stale_bundle_component_labels(result.get("bundle_component_compare"))
    assert stale == plat["expected_stale_labels"]
    smbus = next(
        r for r in result.get("bundle_component_compare") or [] if r.get("label") == "SMBus"
    )
    assert smbus.get("installed_version") == "2.0.0.26"
    assert smbus.get("offer_version") == "5.12.0.44"
    assert smbus.get("vs_offer") == "newer"


def test_alienware_fixture_export_lines() -> None:
    data = _load_fixture()
    plat = data["chipset_platform"]
    entry = {
        "device_name": plat["device_key"],
        "bundle_component_compare": [
            {
                "label": "SMBus",
                "installed_version": "2.0.0.26",
                "offer_version": "5.12.0.44",
                "vs_offer": "newer",
            }
        ],
        "bundle_compare_note": "Bundle wrapper matches but component(s) behind offer manifest: SMBus.",
    }
    lines = bv.format_bundle_compare_export_lines(entry)
    assert any("SMBus" in ln and "Stale" in ln for ln in lines)


def test_probe_summary_matches_fixture_expectations() -> None:
    from live_probe_gating import bundle_verification_probe_summary

    data = _load_fixture()
    plat = data["chipset_platform"]
    comparison = {
        "status": plat["wrapper_status"],
        "bundle_status_rollup": plat["expected_rollup_status"],
        "bundle_component_compare": [
            {
                "label": label,
                "installed_version": next(
                    c["version"]
                    for c in plat["installed_components"]
                    if c["label"] == label
                ),
                "offer_version": next(
                    c["version"]
                    for c in plat["offer_bundle_components"]
                    if c["label"] == label
                ),
                "vs_offer": "newer" if label in plat["expected_stale_labels"] else "same",
            }
            for label in {c["label"] for c in plat["installed_components"]}
        ],
        "bundle_compare_note": "Bundle wrapper matches but component(s) behind offer manifest: SMBus.",
    }
    summary = bundle_verification_probe_summary(comparison)
    assert summary["rollup_status"] == "newer"
    assert summary["stale_components"] == ["SMBus"]
    assert summary["wrapper_status"] == "same"
    assert summary["final_status"] == "newer"
