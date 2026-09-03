"""Guard against UI-thread catalog WMI/PowerShell (Not Responding regressions)."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest import mock

_TESTS_DIR = Path(__file__).resolve().parent
_ROOT = _TESTS_DIR.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
if str(_TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(_TESTS_DIR))

import driver_catalog as drvcat

from gui_test_harness import offscreen_main_window


def test_catalog_ctx_from_profile_never_sync_extends() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        with offscreen_main_window(tmp) as win:
            win._hardware_profile = {"system_ctx": {"system_model": "TestBox"}}
            with mock.patch.object(
                drvcat,
                "extend_system_ctx_for_catalog",
                side_effect=AssertionError("sync extend on UI thread"),
            ):
                ctx = win._catalog_system_ctx_from_profile()
            assert ctx == {"system_model": "TestBox"}


def test_portable_mismatch_skipped_during_driver_scan() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        with offscreen_main_window(tmp) as win:
            win._hardware_profile = {
                "system_ctx": {
                    "system_manufacturer": "Dell Inc.",
                    "system_model": "Alienware m17 R5 AMD",
                }
            }
            fake_thread = mock.MagicMock()
            fake_thread.isRunning.return_value = True
            win._drv_thread = fake_thread
            with mock.patch.object(
                drvcat,
                "extend_system_ctx_for_catalog",
                side_effect=AssertionError("sync extend during scan"),
            ):
                win._maybe_notify_portable_cache_mismatch()
            win._drv_thread = None


def test_stale_prompt_deferred_not_on_tab_handler_stack() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        with offscreen_main_window(tmp) as win:
            calls: list[str] = []
            win._maybe_prompt_stale_catalog_refresh = lambda: calls.append("prompt")  # type: ignore[method-assign]
            win._defer_stale_catalog_refresh_prompt()
            assert calls == []
            from PySide6 import QtWidgets

            app = QtWidgets.QApplication.instance()
            assert app is not None
            app.processEvents()
            assert calls == ["prompt"]


def test_drv_catalog_thread_busy_while_starting() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        with offscreen_main_window(tmp) as win:
            win._drv_thread_starting = True
            assert win._drv_catalog_thread_busy()
            fake_thread = mock.MagicMock()
            fake_thread.isRunning.return_value = False
            win._drv_thread = fake_thread
            assert win._drv_catalog_thread_busy()
            win._drv_thread_starting = False
            assert not win._drv_catalog_thread_busy()


def test_severity_banner_hidden_on_drivers_and_firmware_tabs() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        with offscreen_main_window(tmp) as win:
            assert hasattr(win, "_severity_banner")
            win._severity_banner.setVisible(True)
            for idx in (win._drivers_tab_index(), win._firmware_tab_index()):
                win.tabs.setCurrentIndex(idx)
                win._sync_global_toolbar_for_tab(idx)
                assert not win._severity_banner.isVisible()
            win.tabs.setCurrentIndex(0)
            win._sync_global_toolbar_for_tab(0)
            assert win._severity_banner.isVisible()


def test_footer_install_visible_on_drivers_tab_only() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        with offscreen_main_window(tmp) as win:
            win._sync_global_toolbar_for_tab(win._drivers_tab_index())
            assert win.drv_btn_install.isVisible()
            assert not win.fw_btn_download.isVisible()
            win._sync_global_toolbar_for_tab(0)
            assert not win.drv_btn_install.isVisible()


if __name__ == "__main__":
    test_catalog_ctx_from_profile_never_sync_extends()
    test_portable_mismatch_skipped_during_driver_scan()
    test_stale_prompt_deferred_not_on_tab_handler_stack()
    test_drv_catalog_thread_busy_while_starting()
    test_severity_banner_hidden_on_drivers_and_firmware_tabs()
    test_footer_install_visible_on_drivers_tab_only()
    print("GUI main-thread guard tests OK")
