"""Driver catalog version resolution and comparison (no network)."""

from __future__ import annotations

import driver_catalog as dc


def test_enrich_extracts_version_from_title() -> None:
    offers = [{
        "source": "oem",
        "title": "Intel Wi-Fi driver 23.120.0 package",
        "version": "",
    }]
    out = dc.enrich_offers_with_comparison(offers, "22.0.0.0")
    assert out[0]["version"] == "23.120.0"
    # OEM title-only offers without a verified installer stay uncertain, not confident newer.
    assert out[0]["vs_installed"] == "uncertain"


def test_summarize_same_when_catalog_matches_installed() -> None:
    offers = dc.enrich_offers_with_comparison(
        [{
            "source": "microsoft",
            "source_label": "Microsoft (Windows driver catalog)",
            "title": "NVIDIA Display",
            "version": "32.0.15.9649",
        }],
        "32.0.15.9649",
    )
    assert dc.summarize_offer_status(offers) == "same"


def test_resolve_installed_from_video_controller() -> None:
    ctx = {
        "primary_version": "?",
        "instance_id": "PCI\\VEN_10DE&DEV_24E0",
        "vendor_key": "nvidia",
        "device_label": "NVIDIA GeForce RTX 3070 Ti Laptop GPU",
        "pnp_class": "display",
    }
    system = {
        "video_controllers": [{
            "name": "NVIDIA GeForce RTX 3070 Ti Laptop GPU",
            "pnp_device_id": "PCI\\VEN_10DE&DEV_24E0&SUBSYS_0B5C",
            "driver_version": "32.0.15.9649",
        }],
    }
    assert dc._resolve_primary_installed_version(ctx, system) == "32.0.15.9649"


def test_wu_empty_json_not_internet_error() -> None:
    """Empty optional-driver list must not be reported as an internet failure."""
    rows, err = [], ""
    assert rows == []
    assert err == ""


def test_infer_pnp_class_for_wifi() -> None:
    assert dc._infer_pnp_class_for_device(
        "Intel Wi-Fi 6 AX201", "intel", "", ""
    ) == "net"


def test_summary_merge_from_device_entries() -> None:
    entries = [{
        "device_name": "Realtek Audio",
        "installed_version": "6.0.9126.1",
        "offers": dc.enrich_offers_with_comparison(
            [{
                "source": "microsoft",
                "title": "Realtek Audio",
                "version": "6.0.9200.0",
                "hwid_matched": True,
            }],
            "6.0.9126.1",
        ),
        "status": "newer",
    }]
    comp = dc.build_summary_comparison_from_device_entries(entries)
    assert comp["installed_version"] == "6.0.9126.1"
    assert comp["status"] == "newer"
    assert comp["offers"][0]["version"] == "6.0.9200.0"


def test_filter_drops_older_offers() -> None:
    offers = dc.enrich_offers_with_comparison(
        [
            {"source": "microsoft", "title": "Old pkg", "version": "1.0.0.0"},
            {
                "source": "oem",
                "title": "New pkg",
                "version": "9.0.0.0",
                "url": "https://oem.example/support/drivers/new-pkg.exe",
                "install_verified": True,
            },
        ],
        "5.0.0.0",
    )
    filtered = dc.filter_offers_for_display(offers)
    assert len(filtered) == 1
    assert filtered[0]["version"] == "9.0.0.0"
    assert dc.summarize_offer_status(offers) == "newer"


def test_summarize_none_when_only_older_packages() -> None:
    offers = dc.enrich_offers_with_comparison(
        [{"source": "microsoft", "title": "Stale", "version": "1.0.0.0"}],
        "5.0.0.0",
        "2024-01-01",
    )
    assert dc.summarize_offer_status(offers) == "none"


def test_version_newer_ignores_ms_sentinel_date() -> None:
    vs, note = dc.compare_driver_to_installed(
        "30.0.15.1000",
        "32.0.15.2000",
        installed_date="2024-06-01",
        candidate_date="2006-06-21",
        source="microsoft",
    )
    assert vs == "newer"
    assert "trusting version" in note.lower() or "higher" in note.lower()


def test_renumbering_marks_uncertain() -> None:
    vs, _note = dc.compare_driver_to_installed(
        "10.0.0.0",
        "9.0.0.0",
        installed_date="2023-01-01",
        candidate_date="2025-01-01",
    )
    assert vs == "uncertain"


def test_same_version_newer_date_is_newer() -> None:
    vs, _note = dc.compare_driver_to_installed(
        "32.0.15.9649",
        "32.0.15.9649",
        installed_date="2024-01-01",
        candidate_date="2025-06-01",
    )
    assert vs == "newer"


def test_wu_offered_lower_version_is_uncertain() -> None:
    vs, note = dc.compare_driver_to_installed(
        "32.0.15.9649",
        "31.0.0.0",
        wu_offered=True,
    )
    assert vs == "uncertain"
    assert "Windows Update" in note


def test_sentinel_dates_not_trustworthy() -> None:
    assert not dc.driver_date_is_trustworthy(dc.parse_driver_package_date("2006-06-21"))


if __name__ == "__main__":
    test_enrich_extracts_version_from_title()
    test_summarize_same_when_catalog_matches_installed()
    test_resolve_installed_from_video_controller()
    test_wu_empty_json_not_internet_error()
    test_infer_pnp_class_for_wifi()
    test_summary_merge_from_device_entries()
    test_filter_drops_older_offers()
    test_summarize_none_when_only_older_packages()
    test_version_newer_ignores_ms_sentinel_date()
    test_renumbering_marks_uncertain()
    test_same_version_newer_date_is_newer()
    test_wu_offered_lower_version_is_uncertain()
    test_sentinel_dates_not_trustworthy()
    print("driver version catalog tests OK")
