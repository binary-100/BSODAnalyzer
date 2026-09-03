"""Wave 3 — platform matrix, CDB arch, a11y, dead-code helpers."""

from __future__ import annotations

import sys
from unittest import mock

import bsod_analyzer as core
import bsod_minidump as mdmp
import driver_catalog as drvcat
from gui_widgets import SeverityMeter


def test_cdb_search_arch_dirs_on_x64() -> None:
    with mock.patch.object(mdmp, "_cdb_arch_dir", return_value="x64"):
        assert core._cdb_search_arch_dirs() == ["x64"]


def test_cdb_search_arch_dirs_on_arm64() -> None:
    with mock.patch.object(mdmp, "_cdb_arch_dir", return_value="arm64"):
        assert core._cdb_search_arch_dirs() == ["arm64", "x64"]


def test_windows_osid_non_windows() -> None:
    with mock.patch.object(drvcat.sys, "platform", "linux"):
        assert drvcat._windows_osid() == ""


def test_severity_meter_accessible_description() -> None:
    import sys
    from pathlib import Path

    _tests = Path(__file__).resolve().parent
    if str(_tests) not in sys.path:
        sys.path.insert(0, str(_tests))
    from gui_test_harness import offscreen_application

    with offscreen_application():
        meter = SeverityMeter()
        meter.set_level(2)
        assert "High" in (meter.accessibleDescription() or "")


def test_report_storage_wmi_bundle_none_on_ps_failure() -> None:
    from bsod_hardware_wmi import get_report_storage_wmi_bundle

    with mock.patch("bsod_hardware_wmi.run_powershell", return_value=(False, "")):
        assert get_report_storage_wmi_bundle() is None


if __name__ == "__main__":
    test_cdb_search_arch_dirs_on_x64()
    test_cdb_search_arch_dirs_on_arm64()
    test_windows_osid_non_windows()
    test_severity_meter_accessible_description()
    test_report_storage_wmi_bundle_none_on_ps_failure()
    print("Wave 3 platform/a11y tests OK")
