"""v6 Batch 5 — advanced Microsoft layer (WU strategies, catalog metadata, per-HWID)."""

from __future__ import annotations

from unittest import mock

import catalog_ps_module as cps
import driver_catalog as dc


def test_wu_search_criteria_count() -> None:
    assert len(dc._WU_DRIVER_SEARCH_CRITERIA) >= 3


def test_merge_wu_rows_dedupes_by_update_id() -> None:
    rows = dc._merge_wu_rows_by_update_id([
        [{"UpdateId": "a", "Title": "Driver 1", "Version": "1.0"}],
        [{"UpdateId": "a", "Title": "Driver 1 dup", "Version": "1.0"}, {"UpdateId": "b", "Title": "Driver 2"}],
    ])
    assert len(rows) == 2
    ids = {r["UpdateId"] for r in rows}
    assert ids == {"a", "b"}


def test_online_store_hwid_candidates_subsys_first() -> None:
    ctx = {
        "instance_id": "PCI\\VEN_10DE&DEV_2484&SUBSYS_0B5C1234&REV_A1",
    }
    cands = dc._online_store_hwid_candidates(ctx)
    assert cands[0].upper().startswith("PCI\\VEN_10DE")
    assert "SUBSYS" in cands[0].upper()


def test_allow_per_hwid_requires_v6_and_hwid() -> None:
    ctx = {"instance_id": "PCI\\VEN_10DE&DEV_2484"}
    with mock.patch.object(dc, "_v6_catalog_enabled", return_value=True):
        assert dc._allow_per_hwid_online_store(ctx) is True
    assert dc._allow_per_hwid_online_store({}) is False


def test_per_hwid_skips_gui_all_block() -> None:
    ctx = {"instance_id": "PCI\\VEN_8086&DEV_2723"}
    dc.set_gui_application_mode(True)
    try:
        with mock.patch.object(dc, "_v6_catalog_enabled", return_value=True):
            assert dc._should_skip_online_driver_store(ctx=ctx) is False
            assert dc._should_skip_online_driver_store(ctx={}) is True
    finally:
        dc.set_gui_application_mode(False)


def test_resolve_catalog_row_version_from_filenames() -> None:
    row = {
        "Title": "Realtek LAN driver",
        "Version": "",
        "Description": "",
        "FileNames": ["netrtwlane_6015.1.123.456.cab"],
    }
    ver = cps._resolve_catalog_row_version(row, row["Title"])
    assert ver == "6015.1.123.456"


def test_catalog_tier_preview() -> None:
    assert cps._catalog_tier_from_title("Intel Wi-Fi driver Preview") == "preview"
    assert cps._catalog_tier_from_title("NVIDIA Display WHQL") == "whql"


def test_catalog_include_preview_default_off() -> None:
    dc.configure_catalog(catalog_include_preview=False)
    assert dc.catalog_include_preview_updates() is False


def test_catalog_stale_when_missing() -> None:
    import catalog_cache as ccat

    with mock.patch.object(ccat, "_read_json", return_value=None):
        with mock.patch.object(
            ccat.app_set, "allows_catalog_disk_cache", return_value=True
        ):
            assert ccat.is_catalog_stale() is True


if __name__ == "__main__":
    test_wu_search_criteria_count()
    test_merge_wu_rows_dedupes_by_update_id()
    test_online_store_hwid_candidates_subsys_first()
    test_allow_per_hwid_requires_v6_and_hwid()
    test_per_hwid_skips_gui_all_block()
    test_resolve_catalog_row_version_from_filenames()
    test_catalog_tier_preview()
    test_catalog_include_preview_default_off()
    test_catalog_stale_when_missing()
    print("Microsoft batch 5 tests OK")
