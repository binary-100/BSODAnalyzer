"""Driver update workflow without prior crash analysis."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest import mock

import bsod_analyzer as core
import bsod_workflow as wf
from gui_mixin_catalog import ExportFileChoices
from tests.gui_test_harness import offscreen_main_window


def test_need_hardware_banner_no_analysis_required() -> None:
    text = wf.drv_workflow_banner_text(
        full_install=False,
        crash_context=False,
        hardware_ready=False,
        phase="need_hardware",
    )
    assert "no crash analysis required" in text.lower()


def test_refresh_device_list_starts_hardware_scan_without_profile() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        with offscreen_main_window(tmp) as win:
            win._hardware_profile = None
            win._last_model = None
            with mock.patch.object(win, "_start_hardware_scan") as scan:
                win._start_load_all_driver_devices(force_refresh=True)
                assert win._pending_load_all_drivers_after_hw == (True, False)
                scan.assert_called_once_with(force_refresh_cache=True)


def test_driver_search_blocked_without_profile_until_load() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        with offscreen_main_window(tmp) as win:
            win._hardware_profile = None
            win._last_model = None
            with mock.patch.object(win, "_start_hardware_scan") as scan:
                with mock.patch(
                    "PySide6.QtWidgets.QMessageBox.information"
                ) as msgbox:
                    win._on_begin_driver_update_workflow()
                    scan.assert_not_called()
                    msgbox.assert_called_once()
                    assert win._after_hw_driver_search is None
                    assert not win.drv_btn_check.isEnabled()


def test_can_search_with_inventory_without_analysis() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        with offscreen_main_window(tmp) as win:
            win._last_model = None
            win._hardware_profile = {
                "bios_driver_info": {
                    "device_inventory": [
                        {
                            "name": "ROOT\\NIC",
                            "display_name": "Test NIC",
                            "version": "1.0",
                            "_common_hw": True,
                        }
                    ]
                },
                "system_ctx": {},
            }
            assert not win._has_crash_analysis_context()
            assert win._can_search_drivers_without_full_list()


def test_device_list_load_failure_cancels_chained_search() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        with offscreen_main_window(tmp) as win:
            win._after_hw_driver_search = "checked"
            win.drv_btn_check.setEnabled(False)
            win._drv_all_load_quiet = True
            with mock.patch.object(win, "_show_actionable_error"):
                win._on_drv_all_devices_load_failed("WMI timeout")
            assert win._after_hw_driver_search is None
            assert not win.drv_btn_check.isEnabled()


def test_scan_for_devices_starts_load_without_chaining_search() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        with offscreen_main_window(tmp) as win:
            win._hardware_profile = None
            win._last_model = None
            with mock.patch.object(win, "_start_load_all_driver_devices") as load:
                win._on_scan_for_devices()
                assert win._after_hw_driver_search is None
                load.assert_called_once_with(force_refresh=True, quiet=False)


def test_export_routes_to_unified_export_without_analysis() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        with offscreen_main_window(tmp) as win:
            win._full_report = ""
            win._last_model = None
            win._driver_batch_comparison = {
                "fetched_at": "2026-01-01T00:00:00",
                "devices": [
                    {
                        "device_name": "ROOT\\NIC",
                        "installed_version": "1.0",
                        "status": "newer",
                        "offers": [{"title": "NIC update", "version": "2.0"}],
                    }
                ],
            }
            with mock.patch.object(win, "_export_available_data") as export:
                win.on_export()
                export.assert_called_once()


def test_export_prompts_when_no_crash_or_catalog_data() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        with offscreen_main_window(tmp) as win:
            win._full_report = ""
            win._last_model = None
            win._driver_batch_comparison = None
            with mock.patch(
                "PySide6.QtWidgets.QMessageBox.information"
            ) as msgbox:
                win._export_available_data()
                msgbox.assert_called_once()
                assert "Run Analysis" in msgbox.call_args[0][2]
                assert "Load devices" in msgbox.call_args[0][2]


def test_unified_export_writes_selected_files() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        with offscreen_main_window(tmp) as win:
            win._full_report = "crash report body"
            payload = {
                "drivers": [
                    {
                        "device_name": "ROOT\\NIC",
                        "display_name": "Test NIC",
                        "status": "newer",
                        "installed_version": "1.0",
                        "offers": [],
                    }
                ],
                "firmware": [],
            }
            out_dir = Path(tmp) / "export"
            out_dir.mkdir()
            choices = ExportFileChoices(
                include_crash_report=True,
                include_catalog_summary=True,
                include_catalog_json=True,
            )
            file_entries, summary = win._write_session_export_files(
                out_dir,
                catalog_payload=payload,
                choices=choices,
            )
            assert len(file_entries) == 3
            names = [path.name for _, path in file_entries]
            assert any(n.startswith("BSODAnalyzer_crash_report_") for n in names)
            assert any(
                n.startswith("BSODAnalyzer_driver_firmware_summary_") for n in names
            )
            assert any(n.startswith("BSODAnalyzer_catalog_scan_") for n in names)
            crash_path = next(
                path for label, path in file_entries if "Crash report" in label
            )
            assert crash_path.read_text(encoding="utf-8") == "crash report body"
            assert "Driver & firmware summary" in summary


def test_export_choices_auto_select_single_crash_option() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        with offscreen_main_window(tmp) as win:
            options = win._export_file_options(has_crash=True, has_catalog=False)
            choices = win._prompt_export_file_choices(options)
            assert choices is not None
            assert choices.include_crash_report
            assert not choices.include_catalog_summary
            assert not choices.include_catalog_json


def test_export_choices_all_on_for_catalog_only() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        with offscreen_main_window(tmp) as win:
            options = win._export_file_options(has_crash=False, has_catalog=True)
            choices = win._export_file_choices_all_on(options)
            assert not choices.include_crash_report
            assert choices.include_catalog_summary
            assert choices.include_catalog_json


def test_gather_report_data_merges_full_driver_inventory() -> None:
    full_rows = [{"name": f"Device {i}", "version": "1.0"} for i in range(50)]
    subset = [{"name": "GPU", "version": "1.0"}]
    with mock.patch(
        "bsod_analyzer.query_bugcheck_events",
        return_value=([], False),
    ), mock.patch(
        "bsod_analyzer.get_logged_in_user_paths",
        return_value=("user", r"C:\CrashDumps", [r"C:\CrashDumps"]),
    ), mock.patch(
        "bsod_analyzer.list_dumps",
        return_value=[],
    ), mock.patch(
        "bsod_analyzer.check_full_dump",
        return_value=None,
    ), mock.patch(
        "bsod_analyzer.list_dumps_from_paths",
        return_value=[],
    ), mock.patch(
        "bsod_analyzer.query_application_crashes",
        return_value=[],
    ), mock.patch(
        "bsod_analyzer.get_bios_and_driver_versions",
        return_value={"device_inventory": subset, "drivers": subset},
    ), mock.patch(
        "bsod_analyzer.get_dump_config",
        return_value=(1, "Small memory dump (minidump)"),
    ), mock.patch(
        "bsod_analyzer.find_cdb",
        return_value=None,
    ), mock.patch(
        "bsod_analyzer.query_whea_hardware_errors",
        return_value=[],
    ), mock.patch(
        "bsod_analyzer.query_thermal_events",
        return_value=[],
    ), mock.patch(
        "bsod_analyzer.get_pnp_entities_for_analysis",
        return_value=[],
    ), mock.patch(
        "bsod_analyzer.get_storage_and_system_context",
        return_value={},
    ), mock.patch(
        "bsod_analyzer.get_report_storage_wmi_bundle",
        return_value={},
    ), mock.patch(
        "bsod_analyzer.get_all_installed_driver_devices",
        return_value=full_rows,
    ):
        fmt_args, _needs = core.gather_report_data(include_reliability=False)
    bio = fmt_args[13]
    all_d = bio.get("all_drivers") or []
    assert len(all_d) == len(full_rows)
    assert len(all_d) > len(subset)


def test_analysis_full_inventory_enables_search_without_reload() -> None:
    full = [{"name": f"dev{i}", "version": "1"} for i in range(50)]
    subset = [{"name": "gpu", "version": "1"}]
    with tempfile.TemporaryDirectory() as tmp:
        with offscreen_main_window(tmp) as win:
            win._apply_hardware_profile(
                {
                    "bios_driver_info": {
                        "all_drivers": full,
                        "device_inventory": subset,
                        "drivers": subset,
                    },
                    "system_ctx": {},
                },
                update_drivers_tab=False,
            )
            assert win._all_devices_loaded
            assert win._session_hw_inventory_ready
            assert len(win._session_all_drivers) == 50
            need_hw, _ = win._needs_hardware_profile_scan()
            assert not need_hw


def test_drivers_tab_switch_full_list_without_faulting_driver_uses_all_view() -> None:
    from tests.gui_test_harness import minimal_analysis_model

    full = [{"name": f"dev{i}", "version": "1"} for i in range(70)]
    with tempfile.TemporaryDirectory() as tmp:
        with offscreen_main_window(tmp) as win:
            m = dict(minimal_analysis_model())
            m["driver"] = None
            win._last_model = m
            win._session_all_drivers = full
            win._all_devices_loaded = True
            win._hardware_profile = {
                "bios_driver_info": {
                    "device_inventory": full[:5],
                    "drivers": full[:5],
                    "all_drivers_count": len(full),
                },
                "system_ctx": dict(m.get("system_ctx") or {}),
            }
            idx = win._drivers_tab_index()
            assert idx >= 0
            la = win.drv_view_filter.findData("log_attention")
            if la >= 0:
                win.drv_view_filter.setCurrentIndex(la)
            win._on_main_tab_changed(idx)
            assert win.drv_view_filter.currentData() == "all"


def test_ensure_drivers_tab_visible_rows_falls_back_to_all() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        with offscreen_main_window(tmp) as win:
            win._drv_unified_cache = [
                {"name": "dev0", "display_name": "Device 0", "_tier": "normal"},
                {"name": "dev1", "display_name": "Device 1", "_tier": "normal"},
            ]
            la = win.drv_view_filter.findData("log_attention")
            assert la >= 0
            win.drv_view_filter.setCurrentIndex(la)
            win._rebuild_drv_table_display()
            assert not win._drv_table_display
            prof = {"bios_driver_info": {}, "system_ctx": {}}
            assert win._ensure_drivers_tab_visible_rows(prof)
            assert win.drv_view_filter.currentData() == "all"
            assert win._drv_table_display


def test_driver_search_prompts_when_full_list_not_loaded() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        with offscreen_main_window(tmp) as win:
            win._hardware_profile = {
                "bios_driver_info": {"device_inventory": [{"name": "x"}]},
                "system_ctx": {},
            }
            win._session_hw_inventory_ready = True
            win._all_devices_loaded = False
            win.drv_view_filter.setCurrentIndex(0)  # All devices
            with mock.patch.object(win, "_needs_hardware_profile_scan", return_value=(False, "")):
                with mock.patch.object(win, "_populate_drivers_tab"):
                    with mock.patch.object(win, "_start_load_all_driver_devices") as load:
                        with mock.patch(
                            "PySide6.QtWidgets.QMessageBox.information"
                        ) as msgbox:
                            win._on_begin_driver_update_workflow()
                            load.assert_not_called()
                            msgbox.assert_called_once()
                            assert win._after_hw_driver_search is None
                            assert not win.drv_btn_check.isEnabled()


def test_prepare_full_driver_catalog_search_includes_all_devices() -> None:
    """② Search for updates must scan every catalog-eligible row, not crash-linked only."""
    with tempfile.TemporaryDirectory() as tmp:
        with offscreen_main_window(tmp) as win:
            devices = [
                {
                    "name": f"dev{i}",
                    "display_name": f"Device {i}",
                    "_tier": "normal",
                    "_common_hw": i < 3,
                }
                for i in range(8)
            ]
            win._drv_unified_cache = devices
            win._drv_check_excluded = {"dev5", "dev6"}
            win._drv_include_user_customized = True
            la = win.drv_view_filter.findData("log_attention")
            assert la >= 0
            win.drv_view_filter.setCurrentIndex(la)
            win._hardware_profile = {
                "bios_driver_info": {"device_inventory": devices},
                "system_ctx": {},
            }
            win._prepare_full_driver_catalog_search()
            assert win.drv_view_filter.currentData() == "all"
            assert not win._drv_include_user_customized
            names = win._drv_checked_device_names()
            assert len(names) == 8
            assert "dev5" in names and "dev6" in names


def test_system_on_battery_power_non_windows_returns_false() -> None:
    import bsod_runtime as rt

    with mock.patch.object(rt.sys, "platform", "linux"):
        assert rt.system_on_battery_power() is False


def test_write_text_file_sync_notifies_and_persists(tmp_path: Path) -> None:
    import bsod_runtime as rt

    target = tmp_path / "out" / "sample.txt"
    rt.write_text_file_sync(target, "hello")
    assert target.read_text(encoding="utf-8") == "hello"


def test_default_export_directory_is_existing_folder() -> None:
    import app_settings as app_set
    import bsod_runtime as rt

    path = rt.default_export_directory()
    assert path
    assert os.path.isdir(path)
    shell = rt._windows_shell_desktop_path()
    if shell and os.path.isdir(shell):
        if app_set.is_onedrive_synced_path(shell):
            assert os.path.normcase(path) == os.path.normcase(
                str(app_set.local_export_directory())
            )
        else:
            assert os.path.normcase(path) == os.path.normcase(shell)


def test_preferred_export_directory_avoids_onedrive_desktop(tmp_path) -> None:
    """The desktop must be skipped only when it is OneDrive-synced.

    Asserted against the returned directory, not the substring "onedrive": a portable
    checkout can itself live under a OneDrive folder, which says nothing about where
    preferred_export_directory() decided to write.
    """
    import app_settings as app_set

    synced = tmp_path / "OneDrive" / "Desktop"
    plain = tmp_path / "Local" / "Desktop"
    synced.mkdir(parents=True)
    plain.mkdir(parents=True)

    def fake_is_synced(p) -> bool:
        return "onedrive" in str(p).lower()

    with mock.patch.object(app_set, "is_onedrive_synced_path", fake_is_synced):
        with mock.patch(
            "bsod_runtime._windows_shell_desktop_path", return_value=str(synced)
        ):
            picked = Path(app_set.preferred_export_directory({}))
        assert picked != synced
        assert picked == app_set.local_export_directory()

        with mock.patch(
            "bsod_runtime._windows_shell_desktop_path", return_value=str(plain)
        ):
            assert Path(app_set.preferred_export_directory({})) == plain


def test_onedrive_export_destination_warning() -> None:
    import app_settings as app_set

    warn = app_set.onedrive_export_destination_warning(
        r"C:\Users\me\OneDrive\Desktop"
    )
    assert warn
    assert "OneDrive" in warn
    assert app_set.onedrive_export_destination_warning(
        r"C:\Users\me\AppData\Local\BSODAnalyzer\exports"
    ) is None


def test_catalog_installed_columns_match_between_tabs() -> None:
    import os
    import tempfile

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from gui_test_harness import offscreen_main_window
    from gui_theme import DRV_COL_INSTALLED, UNIFIED_TABLE_INSTALLED_COL_WIDTH_WIDE

    with tempfile.TemporaryDirectory() as tmp:
        with offscreen_main_window(tmp) as win:
            drv_w = win.drv_unified_table.columnWidth(DRV_COL_INSTALLED)
            fw_w = win.fw_unified_table.columnWidth(DRV_COL_INSTALLED)
            assert drv_w >= UNIFIED_TABLE_INSTALLED_COL_WIDTH_WIDE
            assert fw_w == drv_w


if __name__ == "__main__":
    test_need_hardware_banner_no_analysis_required()
    test_refresh_device_list_starts_hardware_scan_without_profile()
    test_driver_search_blocked_without_profile_until_load()
    test_can_search_with_inventory_without_analysis()
    test_device_list_load_failure_cancels_chained_search()
    test_scan_for_devices_starts_load_without_chaining_search()
    test_export_routes_to_unified_export_without_analysis()
    test_export_prompts_when_no_crash_or_catalog_data()
    test_unified_export_writes_selected_files()
    test_export_choices_auto_select_single_crash_option()
    test_export_choices_all_on_for_catalog_only()
    test_gather_report_data_merges_full_driver_inventory()
    test_analysis_full_inventory_enables_search_without_reload()
    test_drivers_tab_switch_full_list_without_faulting_driver_uses_all_view()
    test_ensure_drivers_tab_visible_rows_falls_back_to_all()
    test_driver_search_prompts_when_full_list_not_loaded()
    print("Driver-only workflow tests OK")
