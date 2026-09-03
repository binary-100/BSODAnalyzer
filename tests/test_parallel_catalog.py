"""Driver and firmware catalog status-line helpers."""

from __future__ import annotations

import catalog_mscatalog_session as mscat
import driver_catalog as dc
from gui_catalog_parallel import catalog_status_message


def test_gui_catalog_session_refcount_allows_nested_workers() -> None:
    dc.set_gui_catalog_session(False)
    while mscat._GUI_CATALOG_SESSION_DEPTH > 0:  # noqa: SLF001 — test reset
        dc.set_gui_catalog_session(False)
    dc.set_gui_catalog_session(True)
    dc.set_gui_catalog_session(True)
    assert dc._gui_catalog_session_active()  # noqa: SLF001
    dc.set_gui_catalog_session(False)
    assert dc._gui_catalog_session_active()  # noqa: SLF001
    dc.set_gui_catalog_session(False)
    assert not dc._gui_catalog_session_active()  # noqa: SLF001


def test_catalog_status_prefixes_single_worker() -> None:
    drv_only = catalog_status_message("Checking GPU…", drv_running=True, fw_running=False)
    assert drv_only == "Driver update search: Checking GPU…"
    fw_only = catalog_status_message("Checking BIOS…", drv_running=False, fw_running=True)
    assert fw_only == "Firmware update search: Checking BIOS…"
    both = catalog_status_message("Working…", drv_running=True, fw_running=True)
    assert "parallel" not in both.lower()
    assert both == "Driver and firmware searches: Working…"


if __name__ == "__main__":
    test_gui_catalog_session_refcount_allows_nested_workers()
    test_catalog_status_prefixes_single_worker()
    print("Catalog status tests OK")
