"""Regression tests for v6 catalog audit gaps (closed in 6.0.17–6.0.19)."""

from __future__ import annotations

import threading
import time
from unittest import mock

import catalog_export as cexp
import driver_catalog as dc

# The column-layout tests build a bare QTableWidget. Qt aborts the process when a QWidget
# is constructed before any QApplication exists, and again if a parentless widget outlives
# QApplication teardown; offscreen_widget owns both ends. These tests never ran under the
# old runpy runner (no `__main__` block here), so neither problem surfaced until pytest
# started collecting them.
from gui_test_harness import offscreen_widget


def test_merge_export_row_lists_batch_wins() -> None:
    batch = [
        {
            "device_name": "Realtek NIC",
            "status": "newer",
            "offers": [{"version": "1168.28.1224.2025"}],
        }
    ]
    cache = [
        {
            "device_name": "Realtek NIC",
            "status": "same",
            "offers": [{"version": "1125.28.1224.2025"}],
        },
        {"device_name": "Other Device", "status": "none", "offers": []},
    ]
    merged = cexp.merge_export_row_lists(batch, cache)
    assert len(merged) == 2
    by_name = {r["device_name"]: r for r in merged}
    assert by_name["Realtek NIC"]["status"] == "newer"
    assert by_name["Other Device"]["status"] == "none"


def test_is_catalog_stale_when_wu_fresh_oem_stale() -> None:
    import catalog_cache as ccat

    machine = "dell inc.|alienware m17|tag:dz6r1q3"
    wu = {"cached_at": "2026-05-30T00:00:00Z", "machine": machine, "rows": [{}]}
    oem = {"cached_at": "2025-01-01T00:00:00Z", "machine": machine, "offers": [{}]}
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

    def _fresh(blob, settings=None):
        return blob is wu

    with mock.patch.object(ccat, "_read_json", side_effect=_read):
        with mock.patch.object(ccat, "is_catalog_fresh", side_effect=_fresh):
            with mock.patch.object(ccat.app_set, "allows_catalog_disk_cache", return_value=True):
                assert ccat.is_catalog_stale(system_ctx=ctx) is True


def test_parallel_oem_cache_fetches_once() -> None:
    dc.clear_oem_cache()
    dc.configure_catalog(oem_session_cache=True)
    calls = {"n": 0}
    lock = threading.Lock()

    def slow_fetch(_sys: dict | None) -> tuple[list[dict], str]:
        with lock:
            calls["n"] += 1
        time.sleep(0.08)
        return ([{"title": "pkg", "version": "1.0", "url": "https://hp.test"}], "https://hp.test")

    sys_ctx = {"system_manufacturer": "HP", "system_model": "parallel-test"}
    threads = [
        threading.Thread(
            target=dc._cached_oem_rows,
            args=("hp", slow_fetch, sys_ctx),
        )
        for _ in range(4)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)
    assert calls["n"] == 1


def test_chipset_platform_oem_offers_from_cache() -> None:
    try:
        from bsod_analyzer import CHIPSET_DEVICE_AMD
    except ImportError:
        CHIPSET_DEVICE_AMD = "__chipset_amd_platform__"
    ctx = {
        "device_name": CHIPSET_DEVICE_AMD,
        "device_label": "AMD Chipset / Platform drivers",
        "vendor_key": "amd",
        "hw_category": "chipset",
        "primary_version": "8.05.04.516",
    }
    cached = [
        {
            "source": "oem",
            "title": "AMD Chipset Driver",
            "version": "7.12.30.210",
            "category": "Chipset",
        },
        {
            "source": "oem",
            "title": "Realtek Ethernet Driver",
            "version": "1168.28.1224.2025",
            "category": "Network",
        },
    ]
    import catalog_cache as ccat

    with mock.patch.object(ccat, "should_use_disk_cache", return_value=True):
        with mock.patch.object(ccat, "load_oem_offers", return_value=(cached, {})):
            rows = dc._chipset_platform_oem_offers(ctx, {"system_manufacturer": "Dell Inc."})
    assert len(rows) == 1
    assert rows[0]["version"] == "7.12.30.210"


def test_chipset_platform_rejects_adrenalin_version_compare() -> None:
    """Both versions parse but the schemes are unrelated, so the verdict is uncertain.

    "unknown" is for versions we could not read at all; a mismatch we can explain is
    reported as uncertain so the note reaches the user — same as
    test_amd_component_vs_chipset_suite_compare_uncertain.
    """
    vs, note = dc.compare_driver_to_installed("8.05.04.516", "26.7.1")
    assert vs == "uncertain"
    assert "marketing" in note.lower() or "suite" in note.lower()


def test_chipset_pipeline_filters_older_oem_offers() -> None:
    try:
        from bsod_analyzer import CHIPSET_DEVICE_AMD
    except ImportError:
        CHIPSET_DEVICE_AMD = "__chipset_amd_platform__"

    inv = [
        {
            "name": "PCI\\VEN_1022&DEV_15B8&SUBSYS_10281028",
            "display_name": "AMD SMBus Controller",
            "version": "8.05.04.516",
        }
    ]
    sys_ctx = {"system_manufacturer": "Dell Inc.", "system_model": "Alienware m17"}
    newer_oem = {
        "source": "oem",
        "source_label": "OEM (Dell / Alienware)",
        "title": "AMD Chipset Driver",
        "version": "8.05.04.600",
    }
    older_oem = {
        "source": "oem",
        "source_label": "OEM (Dell / Alienware)",
        "title": "AMD Chipset Driver (old)",
        "version": "8.00.00.000",
    }
    with mock.patch.object(dc, "fetch_amd_driver_offers", return_value=[]):
        with mock.patch.object(
            dc,
            "fetch_oem_driver_offers",
            return_value=[newer_oem, older_oem],
        ):
            with mock.patch.object(
                dc,
                "_load_installed_package_versions",
                return_value={"amd_chipset": "8.05.04.516"},
            ):
                dc.clear_installed_package_versions_cache()
                result = dc.build_chipset_platform_comparison(
                    CHIPSET_DEVICE_AMD,
                    sys_ctx,
                    inventory=inv,
                )
    offers = result.get("offers") or []
    versions = {o.get("version") for o in offers if o.get("version")}
    assert "8.05.04.600" in versions
    assert "8.00.00.000" not in versions
    assert result.get("installed_version") == "8.05.04.516"


def test_driver_unified_columns_device_stretch_installed_narrow() -> None:
    from PySide6 import QtWidgets

    import bsod_gui_qt as gui
    from gui_theme import (
        DRV_COL_DEVICE,
        DRV_COL_INSTALLED,
        DRV_COL_STATUS,
        UNIFIED_TABLE_INSTALLED_COL_WIDTH_WIDE,
        UNIFIED_TABLE_STATUS_COL_WIDTH,
    )

    with offscreen_widget(lambda: QtWidgets.QTableWidget(0, 5)) as table:
        gui.MainWindow._configure_drv_unified_columns(table)
        hdr = table.horizontalHeader()
        # Device is the widest, stretching to fill the window; Status is no longer
        # the stretched last section (that made Status widest). Installed keeps a
        # wider fixed width than Status.
        assert hdr.stretchLastSection() is False
        assert hdr.sectionResizeMode(DRV_COL_DEVICE) == QtWidgets.QHeaderView.ResizeMode.Stretch
        assert hdr.sectionResizeMode(DRV_COL_INSTALLED) == QtWidgets.QHeaderView.ResizeMode.Interactive
        assert hdr.sectionResizeMode(DRV_COL_STATUS) == QtWidgets.QHeaderView.ResizeMode.Interactive
        assert table.columnWidth(DRV_COL_INSTALLED) == UNIFIED_TABLE_INSTALLED_COL_WIDTH_WIDE
        assert table.columnWidth(DRV_COL_STATUS) == UNIFIED_TABLE_STATUS_COL_WIDTH
        assert UNIFIED_TABLE_INSTALLED_COL_WIDTH_WIDE > UNIFIED_TABLE_STATUS_COL_WIDTH


def test_driver_package_columns_use_interactive_resize() -> None:
    from PySide6 import QtWidgets

    import bsod_gui_qt as gui

    with offscreen_widget(lambda: QtWidgets.QTableWidget(0, 3)) as table:
        gui.MainWindow._configure_driver_package_columns(table)
        hdr = table.horizontalHeader()
        assert hdr.stretchLastSection() is True
        assert hdr.sectionResizeMode(0) == QtWidgets.QHeaderView.ResizeMode.Interactive
        assert hdr.sectionResizeMode(1) == QtWidgets.QHeaderView.ResizeMode.Interactive
        assert hdr.sectionResizeMode(2) == QtWidgets.QHeaderView.ResizeMode.Stretch


def test_compare_package_columns_fit_without_horizontal_scroll() -> None:
    from PySide6 import QtCore, QtWidgets

    import bsod_gui_qt as gui

    with offscreen_widget(lambda: QtWidgets.QTableWidget(0, 3)) as table:
        table.setHorizontalHeaderLabels(["Compare", "Source", "Package"])
        gui.MainWindow._configure_driver_package_columns(table, compare_table=True)
        hdr = table.horizontalHeader()
        assert (
            table.horizontalScrollBarPolicy()
            == QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        assert hdr.sectionResizeMode(0) == QtWidgets.QHeaderView.ResizeMode.ResizeToContents
        assert hdr.sectionResizeMode(2) == QtWidgets.QHeaderView.ResizeMode.Stretch


def test_balanced_comfortable_is_default_catalog_preset() -> None:
    from gui_theme import (
        CATALOG_LAYOUT_DEFAULT,
        CATALOG_LAYOUT_PRESETS,
        DEFAULT_WINDOW_HEIGHT,
        DEFAULT_WINDOW_WIDTH,
        UNIFIED_TABLE_INSTALLED_COL_WIDTH_WIDE,
        UNIFIED_TABLE_LIST_BODY_MIN_HEIGHT_COMFORT,
    )

    assert CATALOG_LAYOUT_DEFAULT == "balanced_comfortable"
    preset = CATALOG_LAYOUT_PRESETS[CATALOG_LAYOUT_DEFAULT]
    assert preset["splitter"] == (420, 170, 110)
    assert preset["installed_col_width"] == UNIFIED_TABLE_INSTALLED_COL_WIDTH_WIDE
    assert preset["table_min_height"] == UNIFIED_TABLE_LIST_BODY_MIN_HEIGHT_COMFORT
    assert DEFAULT_WINDOW_WIDTH == 1536
    assert DEFAULT_WINDOW_HEIGHT == 960


def test_unified_tab_splitter_favors_device_list() -> None:
    from gui_theme import (
        UNIFIED_TAB_INSPECTOR_MIN_HEIGHT,
        UNIFIED_TAB_LIST_PANEL_MIN_HEIGHT,
        UNIFIED_TAB_PACKAGES_PANEL_MIN_HEIGHT,
        UNIFIED_TAB_SPLITTER_SIZES,
    )

    assert UNIFIED_TAB_SPLITTER_SIZES[0] == UNIFIED_TAB_SPLITTER_SIZES[1]
    assert UNIFIED_TAB_SPLITTER_SIZES[1] == UNIFIED_TAB_SPLITTER_SIZES[2]
    assert UNIFIED_TAB_LIST_PANEL_MIN_HEIGHT == UNIFIED_TAB_INSPECTOR_MIN_HEIGHT
    assert UNIFIED_TAB_INSPECTOR_MIN_HEIGHT == UNIFIED_TAB_PACKAGES_PANEL_MIN_HEIGHT


def test_load_rejects_tagged_blob_without_profile() -> None:
    import catalog_cache as ccat

    blob = {
        "machine": "dell inc.|alienware m17|tag:dz6r1q3",
        "rows": [{"title": "nic"}],
    }
    with mock.patch.object(ccat, "_read_json", return_value=blob):
        rows, err, loaded = ccat.load_wu_rows(None)
    assert rows == []
    assert loaded is None


def test_should_prompt_requires_hardware_identity() -> None:
    import catalog_cache as ccat

    with mock.patch.object(ccat, "is_catalog_stale", return_value=True):
        assert ccat.should_prompt_catalog_refresh(system_ctx=None) is False
        assert ccat.should_prompt_catalog_refresh(system_ctx={}) is False
        ctx = {
            "system_manufacturer": "Dell Inc.",
            "system_model": "Alienware m17",
            "service_tag": "DZ6R1Q3",
        }
        full = {"install_mode": "full", "catalog_auto_refresh_prompt": True}
        assert ccat.should_prompt_catalog_refresh(full, system_ctx=ctx) is True
        portable = {"install_mode": "portable", "catalog_auto_refresh_prompt": True}
        assert ccat.should_prompt_catalog_refresh(portable, system_ctx=ctx) is False


def test_chipset_without_anchor_skips_ms_and_sets_note() -> None:
    note = dc.chipset_ms_catalog_limitation_note(
        {"hw_category": "chipset", "vendor_key": "amd"},
    )
    assert note and "PnP anchor" in note
    with mock.patch.object(dc, "fetch_amd_driver_offers", return_value=[]):
        with mock.patch.object(dc, "fetch_oem_driver_offers", return_value=[]):
            with mock.patch.object(dc, "_microsoft_catalog_task", return_value=lambda: [{"source": "microsoft"}]) as ms:
                try:
                    from bsod_analyzer import CHIPSET_DEVICE_AMD
                except ImportError:
                    CHIPSET_DEVICE_AMD = "__chipset_amd_platform__"
                result = dc.build_chipset_platform_comparison(
                    CHIPSET_DEVICE_AMD,
                    {"system_manufacturer": "Dell Inc.", "system_model": "m17"},
                    inventory=[],
                )
    ms.assert_not_called()
    assert result.get("catalog_note")


def test_persist_oem_skips_live_fallback() -> None:
    import catalog_cache as ccat

    dc.clear_oem_cache()
    sys_ctx = {"system_manufacturer": "Dell Inc.", "system_model": "test"}
    with mock.patch.object(ccat, "save_wu_rows"):
        with mock.patch.object(ccat, "save_oem_offers") as save_oem:
            with mock.patch.object(dc, "fetch_oem_catalog_for_system") as deep:
                dc._WU_DRIVER_ROWS_CACHE = [{"title": "wu"}]
                dc.persist_session_catalog_cache(sys_ctx)
                deep.assert_not_called()
                save_oem.assert_not_called()


def test_backlog_has_no_retired_vendor_api_names() -> None:
    from pathlib import Path

    from scripts.audit_vendor_apis import scan_docs_for_retired_api_names

    root = Path(__file__).resolve().parents[1]
    problems = scan_docs_for_retired_api_names(root)
    assert problems == [], problems


def test_collect_hardcoded_vendor_urls() -> None:
    from pathlib import Path

    from scripts.audit_vendor_apis import (
        collect_hardcoded_vendor_urls,
        scan_code_for_retired_urls,
    )

    root = Path(__file__).resolve().parents[1]
    urls = collect_hardcoded_vendor_urls(root)
    assert any("amd.com" in u for u in urls)
    assert any("nvidia.com" in u for u in urls)
    assert all(u.startswith("https://") for u in urls)
    assert scan_code_for_retired_urls(root) == []


if __name__ == "__main__":
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    import gui_qt_bootstrap as _qt_boot

    _qt_boot.ensure_offscreen_for_tests(probe=False)
    from PySide6 import QtWidgets

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    test_merge_export_row_lists_batch_wins()
    test_is_catalog_stale_when_wu_fresh_oem_stale()
    test_parallel_oem_cache_fetches_once()
    test_chipset_pipeline_filters_older_oem_offers()
    test_driver_unified_columns_device_stretch_installed_narrow()
    test_driver_package_columns_use_interactive_resize()
    test_unified_tab_splitter_favors_device_list()
    test_load_rejects_tagged_blob_without_profile()
    test_should_prompt_requires_hardware_identity()
    test_chipset_without_anchor_skips_ms_and_sets_note()
    test_persist_oem_skips_live_fallback()
    test_backlog_has_no_retired_vendor_api_names()
    test_collect_hardcoded_vendor_urls()
    print("catalog audit coverage tests OK")
