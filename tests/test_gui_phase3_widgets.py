"""Phase 3 — widget interaction tests (PySide6 QtTest, no pytest-qt)."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest import mock

_TESTS_DIR = Path(__file__).resolve().parent
if str(_TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(_TESTS_DIR))

from gui_test_harness import (
    minimal_analysis_model,
    minimal_fmt_args,
    offscreen_main_window,
    process_events_until,
)
from test_gui_phase2_offscreen import _sample_devices


def test_drv_include_checkbox_toggles_row() -> None:
    from PySide6 import QtCore

    with tempfile.TemporaryDirectory() as tmp:
        with offscreen_main_window(tmp) as win:
            win._drv_unified_cache = _sample_devices()
            win._rebuild_drv_table_display()
            win._sync_drv_unified_table()
            process_events_until(
                lambda: not getattr(win, "_drv_table_sync_active", False),
                timeout_ms=2000,
            )
            from gui_theme import DRV_COL_CHECK

            item = win.drv_unified_table.item(0, DRV_COL_CHECK)
            assert item is not None
            item.setCheckState(QtCore.Qt.CheckState.Unchecked)
            win._on_drv_include_item_changed(item)
            assert "Alpha Device" not in win._drv_checked_device_names()
            item.setCheckState(QtCore.Qt.CheckState.Checked)
            win._on_drv_include_item_changed(item)
            assert "Alpha Device" in win._drv_checked_device_names()


def test_drv_view_filter_combo_changes_filter() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        with offscreen_main_window(tmp) as win:
            win._last_model = minimal_analysis_model()
            win._last_fmt_args = minimal_fmt_args()
            win._drv_unified_cache = _sample_devices()
            win._drv_unified_cache[0]["_tier"] = "culprit"
            win._drv_unified_cache[0]["_crash_linked"] = True
            win._rebuild_drv_table_display()
            idx = win.drv_view_filter.findData("log_attention")
            assert idx >= 0
            win.drv_view_filter.setCurrentIndex(idx)
            win._apply_drv_filter()
            process_events_until(
                lambda: not getattr(win, "_drv_table_sync_active", False),
                timeout_ms=2000,
            )
            visible = win._drv_visible_device_names()
            assert visible == ["Alpha Device"]


def test_fw_search_disabled_without_include() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        with offscreen_main_window(tmp) as win:
            win._hardware_profile = {
                "bios_driver_info": {"bios": {"version": "1.0"}},
                "system_ctx": {},
                "pnp_list": [],
                "ssd_firmware": [],
            }
            win._ssd_firmware_loaded = True
            win._populate_firmware_tab(load_support_links=False)
            idx = win.fw_view_filter.findData("log_attention")
            if idx >= 0:
                win.fw_view_filter.setCurrentIndex(idx)
                win._apply_fw_include_column_visibility()
                win._apply_fw_filter()
            win._fw_apply_include_column_states()
            assert not win._fw_checked_target_keys()
            assert not win.fw_btn_check.isEnabled()


def test_fw_search_enabled_after_component_load() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        with offscreen_main_window(tmp) as win:
            win._hardware_profile = {
                "bios_driver_info": {"bios": {"version": "1.0", "manufacturer": "Dell"}},
                "system_ctx": {},
                "pnp_list": [],
                "ssd_firmware": [
                    {"model": "Samsung SSD 990 PRO", "firmware_revision": "8B2QJXD7"},
                ],
                "secondary_firmware": [
                    {
                        "key": "peripheral:046d:c081",
                        "component": "Logitech G900 Gaming Mouse",
                        "installed": "—",
                        "installed_source": "hid_driver",
                        "vendor_key": "logitech",
                        "device_id": r"HID\VID_046D&PID_C081",
                    },
                ],
            }
            win._ssd_firmware_loaded = True
            win._populate_firmware_tab(load_support_links=False)
            assert win._fw_checked_target_keys()
            assert win.fw_btn_check.isEnabled()
            assert win.fw_btn_check.objectName() == "Primary"
            assert win.fw_btn_scan_components.objectName() == ""


def test_fw_load_populates_firmware_tab_once() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        with offscreen_main_window(tmp) as win:
            idx = win._firmware_tab_index()
            if idx >= 0:
                win.tabs.setCurrentIndex(idx)
            win._hardware_profile = {
                "bios_driver_info": {"bios": {"version": "1.0"}},
                "system_ctx": {},
                "pnp_list": [],
            }
            with mock.patch.object(
                win, "_populate_firmware_tab", wraps=win._populate_firmware_tab
            ) as populate:
                win._on_ssd_firmware_loaded(
                    {
                        "ssd": [{"model": "SSD", "firmware_revision": "1"}],
                        "secondary": [],
                    }
                )
                assert populate.call_count == 1


def test_fw_search_enabled_while_load_thread_winding_down() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        with offscreen_main_window(tmp) as win:
            win._hardware_profile = {
                "bios_driver_info": {"bios": {"version": "1.0"}},
                "system_ctx": {},
                "pnp_list": [],
                "ssd_firmware": [{"model": "SSD", "firmware_revision": "1"}],
            }
            win._ssd_firmware_loaded = True
            fake_thread = mock.MagicMock()
            fake_thread.isRunning.return_value = True
            win._ssd_fw_thread = fake_thread
            win._populate_firmware_tab(load_support_links=False)
            assert win._fw_search_button_enabled()
            assert win.fw_btn_check.isEnabled()
            win._ssd_fw_thread = None


def test_fw_search_reenabled_after_reload_clears_include() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        with offscreen_main_window(tmp) as win:
            win._hardware_profile = {
                "bios_driver_info": {"bios": {"version": "1.0"}},
                "system_ctx": {},
                "pnp_list": [],
                "ssd_firmware": [{"model": "SSD", "firmware_revision": "1"}],
            }
            win._ssd_firmware_loaded = True
            win._populate_firmware_tab(load_support_links=False)
            win._fw_clear_all_visible()
            assert not win._fw_checked_target_keys()
            assert not win.fw_btn_check.isEnabled()
            win._fw_include_user_customized = False
            win._apply_fw_include_defaults()
            win._fw_apply_include_column_states()
            win._sync_fw_workflow_buttons()
            assert win._fw_checked_target_keys()
            assert win.fw_btn_check.isEnabled()


def test_catalog_status_line_when_driver_running() -> None:
    from gui_catalog_parallel import catalog_status_message

    msg = catalog_status_message(
        "Checking GPU…",
        drv_running=True,
        fw_running=False,
    )
    assert "parallel" not in msg.lower()
    assert "Driver update search" in msg
    assert "GPU" in msg

    with tempfile.TemporaryDirectory() as tmp:
        with offscreen_main_window(tmp) as win:
            fake_drv = mock.MagicMock()
            fake_drv.isRunning.return_value = True
            win._drv_thread = fake_drv
            win._fw_thread = None
            win._catalog_status_line("Scanning devices…")
            bar_msg = win.statusBar().currentMessage()
            assert "parallel" not in bar_msg.lower()
            assert "Driver update search" in bar_msg


def test_firmware_catalog_blocked_while_driver_catalog_running() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        with offscreen_main_window(tmp) as win:
            win._hardware_profile = {
                "bios_driver_info": {"bios": {"version": "1.0"}},
                "system_ctx": {},
                "pnp_list": [],
                "ssd_firmware": [{"model": "Disk", "firmware": "1"}],
            }
            win._ssd_firmware_loaded = True
            win._fill_fw_unified_table(
                win._build_unified_firmware_list(win._hardware_profile)
            )
            for row in range(win.fw_unified_table.rowCount()):
                item = win.fw_unified_table.item(row, 1)
                if item and item.flags() & item.flags().ItemIsUserCheckable:
                    item.setCheckState(item.checkState().__class__.Checked)
            fake_drv = mock.MagicMock()
            fake_drv.isRunning.return_value = True
            win._drv_thread = fake_drv
            with mock.patch.object(win, "_start_firmware_catalog_check") as start_fw:
                win._on_check_firmware_catalog()
            start_fw.assert_not_called()
            assert "driver" in win.statusBar().currentMessage().lower()


def test_drv_filter_pending_flush_after_table_sync() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        with offscreen_main_window(tmp) as win:
            win._drv_unified_cache = _sample_devices()
            win._rebuild_drv_table_display()
            win._drv_table_sync_active = True
            win._drv_filter_debounce.stop()
            win.drv_filter.setText("alpha")
            win._on_drv_filter_changed()
            assert win._drv_filter_pending
            win._finish_drv_table_sync()
            process_events_until(
                lambda: not getattr(win, "_drv_table_sync_active", False),
                timeout_ms=2000,
            )
            visible = win._drv_visible_device_names()
            assert visible == ["Alpha Device"]


def test_fw_filter_uses_debounce_timer() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        with offscreen_main_window(tmp) as win:
            win._hardware_profile = {
                "bios_driver_info": {"bios": {"version": "1.0"}},
                "system_ctx": {},
                "pnp_list": [],
                "ssd_firmware": [{"model": "Disk", "firmware": "1"}],
            }
            win._ssd_firmware_loaded = True
            entries = win._build_unified_firmware_list(win._hardware_profile)
            for ent in entries:
                ent["_tier"] = "culprit"
                ent["_scan_verified"] = True
                ent["_check_status"] = "newer"
            win._fill_fw_unified_table(entries)
            with mock.patch.object(win, "_apply_fw_filter", wraps=win._apply_fw_filter) as apply_fw:
                idx = win.fw_view_filter.findData("updates")
                assert idx >= 0
                win.fw_view_filter.setCurrentIndex(idx)
                apply_fw.assert_not_called()
                process_events_until(lambda: apply_fw.call_count >= 1, timeout_ms=500)
                assert apply_fw.call_count >= 1


def test_banner_tab_progress_full_width_with_caption() -> None:
    from gui_theme import TASK_PROGRESS_BANNER_FRAME_HEIGHT

    with tempfile.TemporaryDirectory() as tmp:
        with offscreen_main_window(tmp) as win:
            win.tabs.setCurrentIndex(0)
            win._sync_task_progress_layout_for_tab(0)
            win._analysis_run_active = True
            win._begin_task_progress("Reading Windows event logs…", maximum=100, value=8)
            assert win._task_progress_label.isVisible()
            assert win._task_progress.objectName() == "TaskProgressBar"
            assert not win._task_progress.isTextVisible()
            assert win._task_progress_frame.height() == TASK_PROGRESS_BANNER_FRAME_HEIGHT
            lay = win._task_progress_frame.layout()
            assert lay.contentsMargins().left() == 0
            win._end_task_progress()


def test_post_analysis_driver_load_hides_banner_progress() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        with offscreen_main_window(tmp) as win:
            win.tabs.setCurrentIndex(0)
            win._analysis_run_active = False
            win._begin_task_progress("Loading full device list…", maximum=0)
            assert not win._header_progress_visible_on_current_tab(
                "Loading full device list…"
            )
            assert not win._task_progress_frame.isVisible()
            win._end_task_progress()


def test_analysis_progress_mirrors_to_drivers_tab_status() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        with offscreen_main_window(tmp) as win:
            idx = win._drivers_tab_index()
            assert idx >= 0
            win.tabs.setCurrentIndex(idx)
            win._begin_task_progress("Running log analysis…", maximum=100, value=5)
            win._on_progress(8, "Reading Windows event logs…")
            assert "event logs" in win.drv_scan_status.text().lower()
            assert win._task_progress_frame.isVisible()
            win._on_progress(
                35,
                "Driver inventory 2/5 (Realtek PCIe GbE Family Controller)…",
            )
            assert "Driver inventory 2/5" in win.drv_scan_status.text()
            assert "(40%)" in win.drv_scan_status.text()
            win._end_task_progress()


def test_driver_inventory_progress_updates_status_off_tab() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        with offscreen_main_window(tmp) as win:
            win._begin_task_progress("Running log analysis…", maximum=100, value=0)
            win._set_task_progress(
                35,
                "Driver inventory 1/4 (Intel Wi-Fi)…",
                maximum=100,
            )
            assert "Driver inventory 1/4" in win.drv_scan_status.text()
            win._end_task_progress()


def test_tab_switch_refreshes_catalog_status_from_active_progress() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        with offscreen_main_window(tmp) as win:
            win._begin_task_progress("Loading full device list…", maximum=0)
            win._set_task_progress(label="Loading full device list…")
            fw_idx = win._firmware_tab_index()
            drv_idx = win._drivers_tab_index()
            assert fw_idx >= 0 and drv_idx >= 0
            win.tabs.setCurrentIndex(fw_idx)
            win._sync_global_toolbar_for_tab(fw_idx)
            assert "device list" in win.fw_scan_status.text().lower()
            win.tabs.setCurrentIndex(drv_idx)
            win._sync_global_toolbar_for_tab(drv_idx)
            assert "device list" in win.drv_scan_status.text().lower()
            win._end_task_progress()


def test_catalog_tab_progress_bar_full_width_chrome() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        with offscreen_main_window(tmp) as win:
            idx = win._drivers_tab_index()
            assert idx >= 0
            win.tabs.setCurrentIndex(idx)
            win._sync_task_progress_layout_for_tab(idx)
            assert not win._task_progress_label.isVisible()
            assert win._task_progress.minimumWidth() == 0
            assert win._task_progress.objectName() == "TaskProgressBar"
            win._begin_task_progress("Loading full device list…", maximum=0)
            lay = win._task_progress_frame.layout()
            assert lay.contentsMargins().left() == 0
            assert lay.contentsMargins().right() == 0
            win._end_task_progress()


def test_fw_catalog_progress_uses_global_progress_bar() -> None:
    from gui_theme import TASK_PROGRESS_FRAME_HEIGHT

    with tempfile.TemporaryDirectory() as tmp:
        with offscreen_main_window(tmp) as win:
            idx = win._firmware_tab_index()
            if idx >= 0:
                win.tabs.setCurrentIndex(idx)
            win._begin_task_progress("Warming firmware catalogs (batch)…", maximum=0)
            win._on_fw_catalog_progress("Warming firmware catalogs (batch)…")
            global_frame = win._task_progress_frame
            global_bar = win._task_progress
            tab_frame = win.fw_tab_progress_frame
            assert global_frame.isVisible()
            assert global_frame.height() == TASK_PROGRESS_FRAME_HEIGHT
            assert not tab_frame.isVisible()
            assert tab_frame.height() == 0
            assert global_bar.maximum() == 0
            assert "Warming firmware catalogs" in win.fw_scan_status.text()
            win._on_fw_catalog_progress("Checking 3 firmware component(s)")
            assert global_bar.maximum() == 3
            assert global_bar.value() == 0
            win._on_fw_catalog_progress("Checked 1/3 — BIOS")
            assert global_bar.value() == 1
            win._on_fw_catalog_progress("Checked 3/3 — Logitech G900 — finalizing…")
            assert global_bar.value() == 3


if __name__ == "__main__":
    test_drv_include_checkbox_toggles_row()
    test_drv_view_filter_combo_changes_filter()
    test_drv_filter_pending_flush_after_table_sync()
    test_fw_filter_uses_debounce_timer()
    test_fw_search_disabled_without_include()
    test_fw_search_enabled_after_component_load()
    test_fw_load_populates_firmware_tab_once()
    test_fw_search_enabled_while_load_thread_winding_down()
    test_fw_search_reenabled_after_reload_clears_include()
    test_fw_catalog_progress_uses_global_progress_bar()
    test_catalog_status_line_when_driver_running()
    test_firmware_catalog_blocked_while_driver_catalog_running()
    print("Phase 3 GUI widget tests OK")
